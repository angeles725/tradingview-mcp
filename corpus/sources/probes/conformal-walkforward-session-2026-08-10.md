# Preserved session — walk-forward (OOS) conformal validation (2026-08-10)

Live receipt for tvdecision Block 20. `forecast.py conformal --validate` over the
live log POOLED with the 778-forecast backfill. Train 70% (by made_at) -> test 30%.

## Out-of-sample coverage (learn delta on train, measure on held-out test)

```
group                 band nTest   raw  adj_oos  delta_bps
OANDA:AUDUSD|15|4      90    26   0.92   0.88     -1.9
OANDA:AUDUSD|15|4      50    26   0.50   0.38     -1.5   <- OVER-tightened (was already 0.50)
OANDA:CN50USD|15|4     90    20   0.90   0.85     -3.4
OANDA:CN50USD|15|4     50    20   0.65   0.45     -3.6
OANDA:DE30EUR|15|4     90    20   0.95   1.00     +5.3
OANDA:DE30EUR|15|4     50    20   0.65   0.55     -2.0
OANDA:EURUSD|15|4      90    26   0.92   0.88     -0.7
OANDA:EURUSD|15|4      50    26   0.69   0.50     -1.1   <- fixed to nominal
OANDA:GBPUSD|15|4      90    26   0.96   0.81     -2.2
OANDA:GBPUSD|15|4      50    26   0.58   0.38     -1.2   <- OVER-tightened
OANDA:JP225USD|15|4    90    20   1.00   1.00     +7.6
OANDA:JP225USD|15|4    50    20   0.90   0.75     -1.9
OANDA:NAS100USD|15|4   90    20   1.00   1.00     +4.0
OANDA:NAS100USD|15|4   50    20   0.75   0.35     -6.6   <- OVER-tightened badly
OANDA:SPX500USD|15|4   90    25   0.96   0.96     +0.2
OANDA:SPX500USD|15|4   50    25   0.60   0.60     -0.0
OANDA:USDJPY|15|4      90    26   1.00   1.00     -1.5
OANDA:USDJPY|15|4      50    26   0.54   0.54     -0.4
OANDA:XAUUSD|15|4      90    41   0.95   0.98     +5.9
OANDA:XAUUSD|15|4      50    41   0.66   0.63     -2.1
```

## Finding

- 90% band: the correction is fairly STABLE out-of-sample (small deltas, coverage
  stays near nominal; gold/DAX widened toward 0.90-1.00 as intended).
- 50% band: the correction OVER-FITS. On EURUSD it fixes 0.69->0.50, but on
  AUDUSD (0.50->0.38), GBPUSD (0.58->0.38) and NAS100 (0.75->0.35) the train-period
  delta over-tightens the test period BELOW 0.50. The static split-conformal delta
  is estimated on ~30-60 points and goes stale across a vol-regime shift.

## Implication

The in-sample conformal seeding shipped in Block 13 is OPTIMISTIC for the 50% band:
out-of-sample it over-corrects on several markets. Recommended tempering (pending
approval): shrink the delta (apply a fraction), switch the 50% band to ACI online
updating, or restrict the live correction to the more-stable 90% band. The 90%
correction may stand as-is.
