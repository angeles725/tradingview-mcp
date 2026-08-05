#!/usr/bin/env bash
# Gated OHLCV collection hook for OANDA:XAUUSD 15m.
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
SYMBOL="OANDA:XAUUSD"
TF="15"
THROTTLE_MIN=30

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
nohup bash -c "
  cd '$PROJECT' || exit 0
  '$NODE' src/cli/index.js ohlcv --count 300 2>>'$LOG' \
    | '$PY' analysis/collect.py --symbol '$SYMBOL' --tf '$TF' >>'$LOG' 2>&1
  echo \"[\$(date '+%F %T')] collect tick done\" >>'$LOG'
" >/dev/null 2>&1 &

exit 0
