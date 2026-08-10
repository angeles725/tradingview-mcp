#!/usr/bin/env bash
# On-demand forecast SNAPSHOT: run the full read-only chain for ONE symbol and
# print a single consolidated report. This is the manual counterpart to the
# automated hooks (collect-hook.sh + periodic-hook.sh): those keep the calibration
# record honest over time; THIS is the "take a photo right now" tool.
#
# It bundles, in one command and one CDP session:
#   1. Live cone (intraday 15m, h=4 ~ next hour)
#   2. Multi-horizon cones (Daily h=5 ~ week, Weekly h=4 ~ month)
#   3. Confluence report (Fibonacci / RSI / accumulation / candles / scenarios)
#   4. Decision + risk sizer (decide.py — sizes only when a setup clears the gates)
#   5. Multi-symbol screening (watchlist on 1h)
#
# Everything is read-only: no order is placed, no forecast is recorded, the log
# is untouched. The chart is restored to its starting symbol/timeframe at the end.
#
# Usage:
#   bash analysis/snapshot.sh                       # defaults to OANDA:XAUUSD
#   bash analysis/snapshot.sh OANDA:SPX500USD
#   WATCHLIST="OANDA:XAUUSD,OANDA:EURUSD" bash analysis/snapshot.sh OANDA:XAUUSD
#
# Requires TradingView Desktop open with CDP on 127.0.0.1:9222 (local only — a
# cloud cron cannot reach it, which is why this is a hook/manual tool, not a routine).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT" || exit 1

SYMBOL="${1:-OANDA:XAUUSD}"
# Watchlist for the screening pass (step 5). Override via env; defaults to the
# B15-recommended instruments plus the symbol under focus.
WATCHLIST="${WATCHLIST:-OANDA:XAUUSD,OANDA:SPX500USD,OANDA:EURUSD,OANDA:NAS100USD}"
EQUITY="${EQUITY:-10000}"          # for the sizer (decide.py uses its own config default too)
BARS="${BARS:-300}"               # bars to pull per timeframe

NODE="$(command -v node || echo /home/linuxbrew/.linuxbrew/bin/node)"
VENV_PY="$HOME/.local/share/research-sdd-tools/venv/bin/python3"
if [ -x "$VENV_PY" ]; then PY="$VENV_PY"; else PY="$(command -v python3)"; fi
CONF="$PROJECT/corpus/conformal.json"
CONF_ARG=()
[ -f "$CONF" ] && CONF_ARG=(--conformal "$CONF")

# --- preflight: CDP must be reachable, else fail loudly (unlike the silent hooks) ---
if ! curl -s --max-time 4 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo "ERROR: TradingView no responde en CDP 127.0.0.1:9222. Abre TradingView Desktop y reintenta." >&2
  exit 1
fi

# --- remember the starting chart so we can restore it on exit (any exit path) ---
START_STATE="$("$NODE" src/cli/index.js state 2>/dev/null)"
START_SYMBOL="$(printf '%s' "$START_STATE" | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("symbol") or "")' 2>/dev/null)"
restore() {
  [ -n "${START_SYMBOL:-}" ] && "$NODE" src/cli/index.js symbol "$START_SYMBOL" >/dev/null 2>&1
  "$NODE" src/cli/index.js timeframe 15 >/dev/null 2>&1
}
trap restore EXIT

# --- helper: switch symbol+tf, pull bars to a temp file, echo its path ----------
pull() {  # pull <symbol> <tf>
  "$NODE" src/cli/index.js symbol "$1" >/dev/null 2>&1; sleep 2
  "$NODE" src/cli/index.js timeframe "$2" >/dev/null 2>&1; sleep 2
  local f; f="$(mktemp)"
  "$NODE" src/cli/index.js ohlcv --count "$BARS" >"$f" 2>/dev/null
  printf '%s' "$f"
}
# extract just the Monte Carlo cone block from an analyze.py run
cone_of() {  # cone_of <pull_file> <tf> <horizon>
  "$PY" analysis/analyze.py --symbol "$SYMBOL" --tf "$2" --horizon "$3" "${CONF_ARG[@]}" <"$1" 2>/dev/null \
    | sed -n '/MONTE CARLO CONE/,/deliver the BAND/p'
}

echo "=========================================================================="
echo " FORECAST SNAPSHOT   $SYMBOL   $(date '+%F %T')"
echo " (read-only: no order placed, no forecast recorded, log untouched)"
echo "=========================================================================="

# --- 1 + 2: cones at three horizons (intraday / week / month) -------------------
P15="$(pull "$SYMBOL" 15)"
echo; echo "### 1) CONO INTRADÍA — 15m h=4 (~próxima hora)"
"$PY" analysis/analyze.py --symbol "$SYMBOL" --tf 15 --horizon 4 "${CONF_ARG[@]}" <"$P15" 2>/dev/null \
  | sed -n '/VOLATILITY/,/deliver the BAND/p'

PD="$(pull "$SYMBOL" D)"
echo; echo "### 2) CONO DIARIO — h=5 (~1 semana)"
cone_of "$PD" D 5

PW="$(pull "$SYMBOL" W)"
echo; echo "    CONO SEMANAL — h=4 (~1 mes)"
cone_of "$PW" W 4

# --- 3: confluence (reuses the Daily pull) --------------------------------------
echo; echo "### 3) CONFLUENCIA (Diario)"
"$PY" analysis/confluence.py --symbol "$SYMBOL" --tf D <"$PD" 2>/dev/null

# --- 4: decision + risk sizer (reuses the Daily pull) ---------------------------
echo; echo "### 4) DECISIÓN + SIZER (Diario, h=5, equity ref \$$EQUITY, riesgo 1%)"
"$PY" analysis/decide.py --symbol "$SYMBOL" --tf D --horizon 5 <"$PD" 2>/dev/null \
  | sed -n '/DECISION/,/Guardrail/p'

rm -f "$P15" "$PD" "$PW"

# --- 5: multi-symbol screening (1h) — screen.py drives its own CDP switching -----
echo; echo "### 5) SCREENING — watchlist en 1h"
"$PY" analysis/screen.py --symbols "$WATCHLIST" --tfs 60 --horizon 8 2>/dev/null

echo; echo "=========================================================================="
echo " Guardrail: esto MIDE la incertidumbre y aplica gates; NO predice dirección."
echo " Ninguna línea es una orden. Valida en Replay/paper antes de arriesgar dinero."
echo "=========================================================================="
