# Preserved session — calibration integrity: contamination guard, target-dedup, cov50 illusion (2026-08-10)

Live receipt for tvdecision Block 21. Branch `feat/quant-analysis-toolkit`.
Commits `06a03a9` (guard + test), `c6d6812` (purge + fresh forecasts),
`a6dea3a` (data dedup), `6ff2060` (target-dedup code). `make test` → 124 passed
(scipy venv `~/.local/share/research-sdd-tools/venv`, scipy 1.18 / numpy 2.5).

## 1. Cross-symbol contamination found in the resolved log

Two GBPUSD records carried `realized.close` ≈ 159 while GBPUSD trades ≈ 1.35 —
USDJPY's price. Root cause: `score_pending` matures a record via `nearest_close`,
which matches on TIME ONLY, so a mis-filtered multi-symbol live window scored
GBPUSD against USDJPY bars at the same instant.

```
RESET corrupt: OANDA:GBPUSD S0=1.35084 realized.close=159.148 (move +11681.4%) target=1786406400
RESET corrupt: OANDA:GBPUSD S0=1.35082 realized.close=159.016 (move +11671.8%) target=1786408200
```

Effect on the scorecard (gaussian cov90): 64/70 = 0.91 with the corruption →
64/68 = 0.94 excluding it; GBPUSD's spurious 0.625 cov90 → 0.83 clean.

## 2. The guard (defense-in-depth beyond the --symbol filter)

`MAX_REALIZED_JUMP = 0.20`. In `score_pending`, after `nearest_close` returns
`rc`: if `S0 and abs(rc/S0 - 1) > MAX_REALIZED_JUMP` → `continue` (refuse to
score, leave pending for a symbol-correct source). Re-resolve of the 2 rows via
`score --store analysis/data` found no store bar at their target → they stay
honestly PENDING rather than mis-scored.

## 3. Target-based dedup replaces exact-made_at dedup

`_dedupe` key changed `(symbol, tf, made_at_unix, horizon)` →
`(symbol, tf, horizon, target_unix)`. Two forecasts share a target only if built
from the same last bar → genuinely redundant. Merge rule: scored beats unscored,
then freshest `made_at` wins. Also applied inside the `score` command before
`write_log` so the persisted log self-cleans every tick. One-time cleanup:
151 → 135 records (−16 pending duplicates from overlapping hook ticks; 0 resolved
dropped). Idempotent re-run: 135 → 135, 0 dup-groups, 76 resolved intact.

## 4. The pooled-vs-independent cov50 illusion (the headline finding)

Clean live scorecard, gaussian, n=81 scored:

```
POOLED      n=81  cov90=0.91  cov50=0.65
INDEP(neff)  n=9  cov90=1.00  cov50=0.56
overlap: 81 scored -> 9 independent (11% kept)
median |realized move| = 0.064%   mean = 0.111%
```

Per-symbol cov50 (n): AUDUSD 0.67(9) · CN50 0.60(5) · DE30 0.40(5) · EUR 0.75(8)
· GBP 0.62(8) · JP225 0.88(8) · NAS100 0.88(8) · SPX 0.43(7) · USDJPY 0.38(8) ·
XAU 0.73(15) — 0.38..0.88, pure small-n noise.

Reading: the pooled cov50=0.65 counts 81 heavily-overlapping (consecutive-15m,
autocorrelated) forecasts as if independent. Over the independent subset
(n_eff=9) cov50=0.56 — close to nominal 0.50. The recent live regime is very
quiet (median move 0.064%), so price stays inside the inner P25..P75 band → the
pooled count is inflated. Non-overlapping backfill (`IMPROVEMENT-BACKLOG.md`)
already measured cov50 ≈ 0.51 (good). The 50% band is NOT broken; the pooled
number over-states the evidence.

## 5. Backtest corroborates NO-TRADE (ema_trend, hold=8, cost 1.0 bps/side, 300×15m)

```
CN50USD  full CI [-4.76,+6.94] bps  IS +3.22 -> OOS -12.60 (win 14%)  overfit collapse
SPX500   full CI [-7.89,-1.82] bps  net LOSING
NAS100   full CI [-8.48,-0.71] bps  OOS +2.01 but CI includes 0
```

All THIN-SAMPLE (~20 trades) → "too few to conclude". The cone is zero-drift
(p_up≈0.50) so it carries no direction; a trend proxy shows no edge net of costs,
matching `decide.py`'s NO-TRADE gate.
