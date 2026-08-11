#!/usr/bin/env bash
# Calendar-gated periodic forecast hook: ONE monthly forecast per month, and ONE
# weekly forecast every Monday, for the recommended instruments — cone-based
# stop-loss / take-profit, then regenerate the HTML report.
#
# Why a hook, not cloud cron: the forecast needs the LOCAL TradingView chart over
# CDP (127.0.0.1:9222), which a cloud cron cannot reach. This fires on Claude Code
# session events and self-gates by calendar month / ISO week, so it runs at most
# once per period and consumes nothing when TradingView is closed.
#
# Wire in .claude/settings.json under SessionStart (and/or Stop), same as
# collect-hook.sh. Manual test:  bash analysis/periodic-hook.sh --force
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Recommended instruments (per tvdecision B15): best-calibrated + sharpest + gold.
SYMBOLS=("OANDA:XAUUSD" "OANDA:SPX500USD" "OANDA:EURUSD")
TF="D"                                    # forecasts run on the Daily series
FORCE=0; [ "${1:-}" = "--force" ] && FORCE=1

NODE="$(command -v node || echo /home/linuxbrew/.linuxbrew/bin/node)"
VENV_PY="$HOME/.local/share/research-sdd-tools/venv/bin/python3"
if [ -x "$VENV_PY" ]; then PY="$VENV_PY"; else PY="$(command -v python3)"; fi

DATA="$PROJECT/analysis/data"
LOG="$DATA/periodic.log"
MSTAMP="$DATA/.last-month"                 # holds YYYY-MM of last monthly run
WSTAMP="$DATA/.last-week"                  # holds YYYY-Www of last weekly run
REPORT="$PROJECT/corpus/periodic-report.html"
mkdir -p "$DATA"

now_month=$(date +%Y-%m)
now_week=$(date +%G-W%V)                   # ISO year-week
dow=$(date +%u)                            # 1=Mon .. 7=Sun

do_month=0; do_week=0
[ "$FORCE" = 1 ] && { do_month=1; do_week=1; }
[ "$(cat "$MSTAMP" 2>/dev/null)" != "$now_month" ] && do_month=1
# weekly only on Monday (dow=1), once per ISO week
if [ "$dow" = "1" ] && [ "$(cat "$WSTAMP" 2>/dev/null)" != "$now_week" ]; then do_week=1; fi

# Nothing due -> exit cheap, no network.
if [ $do_month -eq 0 ] && [ $do_week -eq 0 ]; then exit 0; fi

# TradingView open? Refused port -> exit quietly.
if ! curl -s --max-time 4 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then exit 0; fi

SYMS="${SYMBOLS[*]}"
nohup bash -c "
  cd '$PROJECT' || exit 0
  syms=($SYMS); primary=\${syms[0]}
  '$NODE' src/cli/index.js timeframe '$TF' >>'$LOG' 2>&1; sleep 2
  for sym in \"\${syms[@]}\"; do
    '$NODE' src/cli/index.js symbol \"\$sym\" >>'$LOG' 2>&1; sleep 3
    PULL=\$(mktemp)
    '$NODE' src/cli/index.js ohlcv --count 300 --expect-symbol \"\$sym\" >\"\$PULL\" 2>>'$LOG'
    if [ $do_month -eq 1 ]; then
      '$PY' analysis/periodic.py --symbol \"\$sym\" --tf '$TF' --period month --side auto --ohlcv-store '$DATA' <\"\$PULL\" >>'$LOG' 2>&1
    fi
    if [ $do_week -eq 1 ]; then
      '$PY' analysis/periodic.py --symbol \"\$sym\" --tf '$TF' --period week --side auto --ohlcv-store '$DATA' <\"\$PULL\" >>'$LOG' 2>&1
    fi
    rm -f \"\$PULL\"
  done
  '$PY' analysis/periodic_report.py --out '$REPORT' >>'$LOG' 2>&1
  '$NODE' src/cli/index.js symbol \"\$primary\" >>'$LOG' 2>&1
  [ $do_month -eq 1 ] && echo '$now_month' >'$MSTAMP'
  [ $do_week -eq 1 ] && echo '$now_week' >'$WSTAMP'
  echo \"[\$(date '+%F %T')] periodic tick (month=$do_month week=$do_week)\" >>'$LOG'
" >/dev/null 2>&1 &

exit 0
