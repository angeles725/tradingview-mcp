#!/usr/bin/env bash
# Refresh ALL calibration artifacts in one lock-coordinated, rate-limited pass.
#
# The direction skill/confidence maps and the cone coverage flag are only as
# current as the data they were fit on. This rebuilds both pools from fresh pulls
# and regenerates every derived artifact:
#   corpus/direction-cal-data.jsonl  -> direction-calibration.json + direction-skill.json
#   corpus/forecasts-backfill-cone.jsonl -> cone-coverage.json
#
# It takes the shared chart lock (so the collect-hook cedes), pulls each symbol x
# timeframe ONCE and feeds both the direction and the cone backfills from it, and
# is rate-limited by a stamp (REFRESH_MIN_AGE, default 3 days) so it can be wired
# to a periodic hook without re-pulling every run. Force with FORCE=1.
#
# Usage:
#   bash analysis/refresh-calibration.sh          # rate-limited
#   FORCE=1 bash analysis/refresh-calibration.sh  # ignore the stamp
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT" || exit 1

NODE="$(command -v node || echo /home/linuxbrew/.linuxbrew/bin/node)"
VENV_PY="$HOME/.local/share/research-sdd-tools/venv/bin/python3"
if [ -x "$VENV_PY" ]; then PY="$VENV_PY"; else PY="$(command -v python3)"; fi

DATA="$PROJECT/analysis/data"
DIR_POOL="$PROJECT/corpus/direction-cal-data.jsonl"
CONE_POOL="$PROJECT/corpus/forecasts-backfill-cone.jsonl"
STAMP="$DATA/.last-refresh-calibration"
REFRESH_MIN_AGE="${REFRESH_MIN_AGE:-259200}"     # 3 days
SYMS="${SYMS:-OANDA:XAUUSD OANDA:XAGUSD OANDA:SPX500USD OANDA:NAS100USD OANDA:US2000USD OANDA:DE30EUR OANDA:WTICOUSD OANDA:USDJPY OANDA:EURUSD OANDA:GBPUSD OANDA:HK33HKD OANDA:JP225USD}"
mkdir -p "$DATA"

# Rate limit (unless FORCE=1)
if [ "${FORCE:-0}" != "1" ] && [ -f "$STAMP" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$STAMP" 2>/dev/null || echo 0) ))
  if [ "$age" -lt "$REFRESH_MIN_AGE" ]; then
    echo "refresh skipped (last run ${age}s ago < ${REFRESH_MIN_AGE}s; FORCE=1 to override)"; exit 0
  fi
fi

if ! curl -s --max-time 4 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo "ERROR: TradingView no responde en CDP 127.0.0.1:9222." >&2; exit 1
fi

# Take the shared chart lock so the collect-hook cedes the chart while we pull.
exec 9>"$DATA/.chart.lock" 2>/dev/null && flock 9 2>/dev/null || true

START_SYMBOL="$("$NODE" src/cli/index.js state 2>/dev/null | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("symbol") or "")' 2>/dev/null)"
restore() { [ -n "${START_SYMBOL:-}" ] && "$NODE" src/cli/index.js symbol "$START_SYMBOL" >/dev/null 2>&1; "$NODE" src/cli/index.js timeframe 15 >/dev/null 2>&1; }
trap restore EXIT

: > "$DIR_POOL"; : > "$CONE_POOL"
declare -A CONE_H=( [D]=5 [W]=4 [M]=3 )

pull() {  # $1 symbol $2 tf -> writes bars to $PULL_F, returns 0 on success
  "$NODE" src/cli/index.js timeframe "$2" >/dev/null 2>&1
  local t
  for t in 1 2 3 4 5 6; do
    sleep 2
    "$NODE" src/cli/index.js ohlcv --count 500 --expect-symbol "$1" >"$PULL_F" 2>/dev/null
    grep -q '"close"' "$PULL_F" && return 0
  done
  return 1
}

echo "=== refresh-calibration: $(echo "$SYMS" | wc -w) simbolos ==="
for sym in $SYMS; do
  "$NODE" src/cli/index.js symbol "$sym" >/dev/null 2>&1; sleep 2
  # direction pool: 15m from the accumulated store (no pull needed)
  "$PY" analysis/direction_backfill.py --store "$DATA" --symbol "$sym" --tf 15 --log "$DIR_POOL" --json >/dev/null 2>&1 || true
  # intraday direction-only TFs
  for tf in 1 60; do
    PULL_F="$(mktemp)"
    pull "$sym" "$tf" && "$PY" analysis/direction_backfill.py --symbol "$sym" --tf "$tf" --log "$DIR_POOL" --json <"$PULL_F" >/dev/null 2>&1 || true
    rm -f "$PULL_F"
  done
  # D/W/M: ONE pull feeds BOTH the direction pool and the cone pool
  for tf in D W M; do
    PULL_F="$(mktemp)"
    if pull "$sym" "$tf"; then
      "$PY" analysis/direction_backfill.py --symbol "$sym" --tf "$tf" --log "$DIR_POOL" --json <"$PULL_F" >/dev/null 2>&1 || true
      "$PY" analysis/backfill.py --symbol "$sym" --tf "$tf" --horizon "${CONE_H[$tf]}" --warmup 60 --log "$CONE_POOL" <"$PULL_F" >/dev/null 2>&1 || true
      echo "  $sym $tf: ok"
    else
      echo "  $sym $tf: skip (race)"
    fi
    rm -f "$PULL_F"
  done
done

echo "=== regenerando artefactos ==="
"$PY" analysis/direction_recalibrate.py --data "$DIR_POOL" --out "$PROJECT/corpus/direction-calibration.json" >/dev/null 2>&1 \
  && echo "  direction-calibration.json OK"
"$PY" analysis/direction_significance.py --data "$DIR_POOL" --out "$PROJECT/corpus/direction-skill.json" --n-boot 3000 >/dev/null 2>&1 \
  && echo "  direction-skill.json OK"
"$PY" analysis/cone_coverage.py --log "$CONE_POOL" --out "$PROJECT/corpus/cone-coverage.json" >/dev/null 2>&1 \
  && echo "  cone-coverage.json OK"

touch "$STAMP"
echo "=== refresh-calibration done (dir pool $(wc -l < "$DIR_POOL"), cone pool $(wc -l < "$CONE_POOL")) ==="
