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
#
# Multi-region coverage: the original FX/metals/US set is extended with four
# CONTINUOUS index CFDs so calibration accumulates across the Asian, European
# and US sessions:
#   CN50USD  China A50 (Asian session)   DE30EUR  DAX / Germany (European)
#   JP225USD Nikkei 225 (Asian session)  NAS100USD Nasdaq 100 (US)
# Only near-24h CFDs are auto-collected. Cash indices (e.g. KRX:KOSPI) are
# INTENTIONALLY EXCLUDED here: recorded near their close, the h-bar target lands
# in the overnight gap where no bar ever prints, so the record can never mature
# and the cone under-states the true overnight-gap risk. Forecast those on demand
# only, while their market is live. See corpus/ multi-market notes.
SYMBOLS=("OANDA:XAUUSD" "OANDA:EURUSD" "OANDA:SPX500USD" "OANDA:USDJPY" "OANDA:GBPUSD" "OANDA:AUDUSD" "OANDA:CN50USD" "OANDA:DE30EUR" "OANDA:JP225USD" "OANDA:NAS100USD")
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
# Learned conformal correction table (generated; refreshed each tick after scoring).
# analyze consumes it to WIDEN recorded cones toward nominal coverage once enough
# matured forecasts exist; until then it is empty and analyze is unaffected.
CONF="$PROJECT/corpus/conformal.json"
# Backfill seed log: non-overlapping historical forecasts from the store, pooled
# with the live log so the conformal table reaches min_n far sooner. Regenerated
# at most every BACKFILL_MAX_AGE seconds (it is deterministic from the store and
# GARCH-heavy, so it is not rebuilt every tick).
BACKFILL="$PROJECT/corpus/forecasts-backfill.jsonl"
BACKFILL_MAX_AGE=43200      # 12h

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
    '$NODE' src/cli/index.js ohlcv --count 300 --expect-symbol \"\$sym\" >\"\$PULL\" 2>>'$LOG'
    # (a) accumulate history  (b) record a next-hour forecast
    '$PY' analysis/collect.py --symbol \"\$sym\" --tf '$TF' <\"\$PULL\" >>'$LOG' 2>&1
    '$PY' analysis/analyze.py --symbol \"\$sym\" --tf '$TF' --horizon '$HORIZON' --conformal '$CONF' --json <\"\$PULL\" 2>>'$LOG' \
      | '$PY' analysis/forecast.py record --store '$DATA' >>'$LOG' 2>&1
    rm -f \"\$PULL\"
  done
  # (c) score ALL matured forecasts in ONE symbol-correct pass: each record is
  # matched against ITS OWN symbol/tf store, so a multi-symbol log never scores
  # one symbol against another's bars, and off-live-window forecasts still score.
  '$PY' analysis/forecast.py score --store '$DATA' >>'$LOG' 2>&1
  # (d) refresh the backfill seed if missing/stale (deterministic from the store,
  # GARCH-heavy -> rate-limited), then refresh the conformal correction table from
  # the live log POOLED with the backfill seed, so the NEXT tick's cones are
  # widened toward nominal coverage without waiting weeks for live maturations.
  bfage=999999999
  [ -f '$BACKFILL' ] && bfage=\$(( \$(date +%s) - \$(stat -c %Y '$BACKFILL' 2>/dev/null || echo 0) ))
  if [ \$bfage -gt $BACKFILL_MAX_AGE ]; then
    bfsyms=\$(IFS=,; echo \"\${syms[*]}\")
    '$PY' analysis/backfill.py --store '$DATA' --symbols \"\$bfsyms\" --tf '$TF' --horizon '$HORIZON' --warmup 60 --reset >>'$LOG' 2>&1
  fi
  '$PY' analysis/forecast.py conformal --conformal-out '$CONF' --extra-log '$BACKFILL' >>'$LOG' 2>&1
  # restore the primary chart if we cycled symbols
  [ \$multi -eq 1 ] && '$NODE' src/cli/index.js symbol \"\$primary\" >>'$LOG' 2>&1
  echo \"[\$(date '+%F %T')] collect+forecast tick done (\${#syms[@]} sym)\" >>'$LOG'
" >/dev/null 2>&1 &

exit 0
