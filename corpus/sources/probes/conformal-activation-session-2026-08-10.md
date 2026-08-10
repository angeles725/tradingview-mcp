# Preserved session — conformal activation via backfill validation (2026-08-10)

Live, in-session receipts for tvdecision Block 13. Analysis + TDD, scipy venv.
Implementation committed `89aa22e` on branch `feat/quant-analysis-toolkit`.

## 1. A/B — OLD cone (GARCH/EWMA on returns) vs NEW cone (GARCH+HAR blend)

778 non-overlapping historical forecasts from the store (warmup=60, h=4, 15m),
10 markets. Analysis script: `scratchpad/ab_cone.py` (experiment, not committed).

```
POOLED old  n=778  cov90=0.907  cov50=0.602  pin_bps=3.574
POOLED new  n=778  cov90=0.920  cov50=0.620  pin_bps=3.531
```
- NEW blend marginally better on pinball (-1.2% pooled; better on 7/10 symbols).
- cov90 already ~nominal (0.91) out-of-sample -> the cone is honest.
- Gold (XAUUSD) and DAX (DE30) are the UNDER-covered 90% bands (0.85-0.87).
- Systematic issue in BOTH cones: 50% band OVER-DISPERSED (~0.60 vs 0.50 target).

## 2. Conformal correction measured on the same 778 (NEW cone)

```
POOLED band 90: delta -1.5bps  cover 0.920->0.902  (n=778)
POOLED band 50: delta -1.6bps  cover 0.620->0.501  (n=778)
```
Per symbol the 90% delta WIDENS gold (+3.7bps) and DAX (+2.7bps) and tightens the
rest; the 50% delta is negative for all ten -> the over-dispersion is a real,
systematic bias, not a counting artifact. (Caveat: cover_adj is measured on the
calibration set; a train/test split is the stricter test.)

## 3. Drift bug found and fixed

`backfill.py` `_cones` claimed "exactly as analyze.py builds them" but used the
OLD GARCH/EWMA-on-returns cone, and `backfill_bars` extracted only close. Root
cause: the cone-sigma recipe was duplicated. Fixed by extracting `quant.cone_sigma`
as the single source of truth, called by BOTH analyze and backfill.

## 4. Seeding the live conformal table (live log POOLED with backfill)

Regenerated the backfill with the NEW cone:
```
backfilled 778 non-overlapping forecasts across 10 symbol(s)
```
Then pooled it into the correction table:
```
$ forecast.py conformal --conformal-out corpus/conformal.json \
    --extra-log corpus/forecasts-backfill.jsonl
conformal corrections: 10 group(s) (min_n=20)
  OANDA:XAUUSD|15|4  gaussian 90%: cover 0.88->0.91  delta +1.6bps (n=131)
  OANDA:DE30EUR|15|4 gaussian 90%: cover 0.88->0.92  delta +2.7bps (n=64)
  OANDA:NAS100USD|15|4 gaussian 90%: cover 0.92->0.92 delta -2.6bps (n=64)
  ... (all 10 symbols, 3 models)
```
Without the backfill the same command reports 0 groups (live log alone is below
min_n=20).

## 5. Applied live end-to-end (gold)

```
without --conformal   P5=4331.41 P25=4343.68 P75=4361.03 P95=4373.25
with    --conformal   P5=4330.72 P25=4345.42 P75=4359.30 P95=4373.95
applied gaussian: delta90_frac=+0.000159  delta50_frac=-0.000399
```
The 90% band widened (gold was under-covered) and the 50% band tightened (the
over-dispersion fix), with P50 and p_up untouched.

## 6. Tests

Full suite green after the refactor and activation: `105 passed` (was 104; +1 for
`cone_sigma`). The new shared recipe is covered by
`test_cone_sigma_shared_recipe_blends_and_falls_back`; the existing backfill tests
still pass with the OHLC-aware `_cones`.
