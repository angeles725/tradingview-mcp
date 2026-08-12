#!/usr/bin/env bash
# Multi-timeframe DIRECTIONAL BIAS for ONE symbol across 1m -> 1M.
# Read-only: pulls OHLCV per timeframe, runs direction.py on each, prints one
# consolidated "up / down / flat + confidence" table with the alignment verdict.
# Restores the starting chart on exit. This is the honest counterpart to the
# zero-drift cones: it reports a LEAN with explicit confidence, never a promise.
#
# Usage:
#   bash analysis/direction.sh                 # OANDA:XAUUSD
#   bash analysis/direction.sh OANDA:EURUSD
#   TFS="D W M" bash analysis/direction.sh OANDA:XAUUSD   # subset of timeframes
#
# Requires TradingView Desktop with CDP on 127.0.0.1:9222.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT" || exit 1

SYMBOL="${1:-OANDA:XAUUSD}"
# High -> low. 240=4h, 60=1h, 15=15m, 1=1m. D/W/M = daily/weekly/monthly.
TFS="${TFS:-M W D 60 15 1}"
BARS="${BARS:-300}"

NODE="$(command -v node || echo /home/linuxbrew/.linuxbrew/bin/node)"
VENV_PY="$HOME/.local/share/research-sdd-tools/venv/bin/python3"
if [ -x "$VENV_PY" ]; then PY="$VENV_PY"; else PY="$(command -v python3)"; fi

if ! curl -s --max-time 4 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo "ERROR: TradingView no responde en CDP 127.0.0.1:9222." >&2
  exit 1
fi

START_STATE="$("$NODE" src/cli/index.js state 2>/dev/null)"
START_SYMBOL="$(printf '%s' "$START_STATE" | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("symbol") or "")' 2>/dev/null)"
restore() {
  [ -n "${START_SYMBOL:-}" ] && "$NODE" src/cli/index.js symbol "$START_SYMBOL" >/dev/null 2>&1
  "$NODE" src/cli/index.js timeframe 15 >/dev/null 2>&1
}
trap restore EXIT

RECORDS="$(mktemp)"
"$NODE" src/cli/index.js symbol "$SYMBOL" >/dev/null 2>&1; sleep 2

for tf in $TFS; do
  "$NODE" src/cli/index.js timeframe "$tf" >/dev/null 2>&1
  f="$(mktemp)"
  ok=0
  # --expect-symbol refuses wrong-symbol bars from the background hook's symbol
  # cycling; retry, letting the feed settle, rather than read another market.
  for try in 1 2 3 4 5 6; do
    sleep 2
    "$NODE" src/cli/index.js ohlcv --count "$BARS" --expect-symbol "$SYMBOL" >"$f" 2>/dev/null
    grep -q '"close"' "$f" && ok=1 && break
  done
  if [ "$ok" -eq 1 ]; then
    if ! "$PY" analysis/direction.py bias --symbol "$SYMBOL" --tf "$tf" <"$f" >>"$RECORDS" 2>/dev/null; then
      echo "  [skip] $tf: direction.py fallo (pocos bars?)" >&2
    fi
  else
    echo "  [skip] $tf: no se pudo jalar OHLCV (contencion del hook)" >&2
  fi
  rm -f "$f"
done

if [ ! -s "$RECORDS" ]; then
  echo "ERROR: ningun timeframe produjo datos." >&2
  rm -f "$RECORDS"; exit 1
fi

"$PY" analysis/direction.py aggregate --symbol "$SYMBOL" <"$RECORDS"
rm -f "$RECORDS"
