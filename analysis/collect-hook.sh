#!/usr/bin/env bash
# Gated OHLCV collection + forecast feedback hook for OANDA:XAUUSD 15m.
#
# On each throttled tick it (a) merges the live window into the persistent store,
# (b) RECORDS a next-hour cone forecast, and (c) SCORES any matured forecasts
# against the accumulated store — building an honest calibration record over time
# (corpus/forecasts.jsonl; inspect with `forecast.py stats`).
#
# Wired to Claude Code SessionStart + Stop. Because it is a hook, it can only
# fire while Claude Code is running in this project — so it consumes NOTHING
# when Claude Code is closed. It collects only when BOTH conditions hold:
#   (1) at least THROTTLE_MIN minutes have passed since the last collection, and
#   (2) TradingView's CDP endpoint is reachable on 127.0.0.1:9222 (TV is open).
# It ALWAYS exits 0 immediately; the actual pull runs detached so Claude is
# never delayed. Failures are logged, never surfaced.
#
# Manual test:  .claude-hook-debug=1  bash analysis/collect-hook.sh

set -uo pipefail

# Resolve the project from this script's own location (analysis/collect-hook.sh)
# so it is not tied to a hardcoded path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Symbols to accumulate each tick. With >1 symbol the detached job briefly cycles
# the live chart and restores the FIRST (primary, gold) at the end. Scoring is
# symbol-correct (score --store), so a multi-symbol log never cross-scores.
SYMBOLS=("OANDA:XAUUSD" "OANDA:EURUSD" "OANDA:SPX500USD" "OANDA:USDJPY" "OANDA:GBPUSD" "OANDA:AUDUSD")
TF="15"
THROTTLE_MIN=30
HORIZON=4          # forecast horizon in bars (4 x 15m = next hour)

# Resolve binaries via PATH, with sensible fallbacks for this machine.
NODE="$(command -v node || echo /home/linuxbrew/.linuxbrew/bin/node)"
VENV_PY="$HOME/.local/share/research-sdd-tools/venv/bin/python3"
if [ -x "$VENV_PY" ]; then PY="$VENV_PY"; else PY="$(command -v python3)"; fi

DATA="$PROJECT/analysis/data"
STAMP="$DATA/.last-collect-${TF}"
LOG="$DATA/collect.log"

mkdir -p "$DATA"

# (1) Throttle — skip if we collected recently. Cheap, no network.
if [ -f "$STAMP" ]; then
  now=$(date +%s)
  last=$(stat -c %Y "$STAMP" 2>/dev/null || echo 0)
  if [ $(( now - last )) -lt $(( THROTTLE_MIN * 60 )) ]; then
    exit 0
  fi
fi

# (2) Is TradingView open? A refused/absent port fails fast; exit quietly if so.
if ! curl -s --max-time 4 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  exit 0
fi

# Both gates passed. Stamp now (so a slow/failed pull still respects the throttle)
# and launch the collection DETACHED — the hook returns instantly.
touch "$STAMP"
SYMS="${SYMBOLS[*]}"
nohup bash -c "
  cd '$PROJECT' || exit 0
  syms=($SYMS)
  primary=\${syms[0]}
  multi=0; [ \${#syms[@]} -gt 1 ] && multi=1
  for sym in \"\${syms[@]}\"; do
    # switch the chart only when accumulating >1 symbol; let it settle before pull
    if [ \$multi -eq 1 ]; then '$NODE' src/cli/index.js symbol \"\$sym\" >>'$LOG' 2>&1; sleep 3; fi
    PULL=\$(mktemp)
    '$NODE' src/cli/index.js ohlcv --count 300 >\"\$PULL\" 2>>'$LOG'
    # (a) accumulate history  (b) record a next-hour forecast
    '$PY' analysis/collect.py --symbol \"\$sym\" --tf '$TF' <\"\$PULL\" >>'$LOG' 2>&1
    '$PY' analysis/analyze.py --symbol \"\$sym\" --tf '$TF' --horizon '$HORIZON' --json <\"\$PULL\" 2>>'$LOG' \
      | '$PY' analysis/forecast.py record >>'$LOG' 2>&1
    rm -f \"\$PULL\"
  done
  # (c) score ALL matured forecasts in ONE symbol-correct pass: each record is
  # matched against ITS OWN symbol/tf store, so a multi-symbol log never scores
  # one symbol against another's bars, and off-live-window forecasts still score.
  '$PY' analysis/forecast.py score --store '$DATA' >>'$LOG' 2>&1
  # restore the primary chart if we cycled symbols
  [ \$multi -eq 1 ] && '$NODE' src/cli/index.js symbol \"\$primary\" >>'$LOG' 2>&1
  echo \"[\$(date '+%F %T')] collect+forecast tick done (\${#syms[@]} sym)\" >>'$LOG'
" >/dev/null 2>&1 &

exit 0
