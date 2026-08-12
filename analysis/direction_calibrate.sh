#!/usr/bin/env bash
# Calibrate the DIRECTIONAL bias across timeframes for ONE symbol.
# For each TF: pull the longest available history (<=500 bars), walk it forward
# (leakage-free, non-overlapping), and print the reliability report — hit-rate vs
# the 50% coin-flip benchmark, per confidence bucket. The 15m TF reads from the
# accumulated store (deeper history) instead of a live pull.
#
# Usage:
#   bash analysis/direction_calibrate.sh                 # OANDA:XAUUSD
#   bash analysis/direction_calibrate.sh OANDA:SPX500USD
#   TFS="D W M" bash analysis/direction_calibrate.sh OANDA:XAUUSD
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT" || exit 1

# Hold the shared chart lock for our whole run so the collect-hook cedes the live
# chart instead of cycling symbols under us (fd 9 stays open until this exits).
mkdir -p "$PROJECT/analysis/data" 2>/dev/null || true
exec 9>"$PROJECT/analysis/data/.chart.lock" 2>/dev/null && flock 9 2>/dev/null || true

SYMBOL="${1:-OANDA:XAUUSD}"
TFS="${TFS:-M W D 60 15 1}"
BARS="${BARS:-500}"

NODE="$(command -v node || echo /home/linuxbrew/.linuxbrew/bin/node)"
VENV_PY="$HOME/.local/share/research-sdd-tools/venv/bin/python3"
if [ -x "$VENV_PY" ]; then PY="$VENV_PY"; else PY="$(command -v python3)"; fi

if ! curl -s --max-time 4 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo "ERROR: TradingView no responde en CDP 127.0.0.1:9222." >&2; exit 1
fi

START_SYMBOL="$("$NODE" src/cli/index.js state 2>/dev/null | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("symbol") or "")' 2>/dev/null)"
restore() {
  [ -n "${START_SYMBOL:-}" ] && "$NODE" src/cli/index.js symbol "$START_SYMBOL" >/dev/null 2>&1
  "$NODE" src/cli/index.js timeframe 15 >/dev/null 2>&1
}
trap restore EXIT

echo "=================================================================="
echo " CALIBRACION DIRECCIONAL  $SYMBOL   (walk-forward, sin lookahead)"
echo "=================================================================="

"$NODE" src/cli/index.js symbol "$SYMBOL" >/dev/null 2>&1; sleep 2
STORE_SYM="$SYMBOL"

for tf in $TFS; do
  # 15m: prefer the accumulated store (deeper than a single 500-bar pull).
  if [ "$tf" = "15" ] && [ -f "analysis/data/$(echo "$SYMBOL" | tr ':' '_')_15.csv" ]; then
    "$PY" analysis/direction_backfill.py --store analysis/data --symbol "$SYMBOL" --tf 15 2>&1
    echo
    continue
  fi
  "$NODE" src/cli/index.js timeframe "$tf" >/dev/null 2>&1
  f="$(mktemp)"; ok=0
  for try in 1 2 3 4 5 6; do
    sleep 2
    "$NODE" src/cli/index.js ohlcv --count "$BARS" --expect-symbol "$SYMBOL" >"$f" 2>/dev/null
    grep -q '"close"' "$f" && ok=1 && break
  done
  if [ "$ok" -eq 1 ]; then
    "$PY" analysis/direction_backfill.py --symbol "$SYMBOL" --tf "$tf" <"$f" 2>&1 \
      || echo "  [skip] $tf: pocos bars para calibrar"
  else
    echo "  [skip] $tf: no se pudo jalar OHLCV (contencion del hook)"
  fi
  echo
  rm -f "$f"
done

echo "=================================================================="
echo " Benchmark = 50% (volado). Brier 0.25 = confianza sin informacion."
echo " Un edge real y persistente en TFs altos justificaria el prior;"
echo " ~50% en todos = el sesgo NO predice, solo describe el estado."
echo "=================================================================="
