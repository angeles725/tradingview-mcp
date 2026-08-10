# Preserved session — per-market forecast ranking (2026-08-10)

Live, in-session receipt for tvdecision Block 15. Per-market calibration computed
with `forecast.calibration()` over the backfill log `corpus/forecasts-backfill.jsonl`
(778 non-overlapping historical forecasts, new cone, gaussian model). Ranking
script run under the scipy venv.

## Per-market table (gaussian, backfill n=62-126 per market)

```
market           n  cov90  cov50  pin_bps  calErr
EURUSD          81   0.94   0.64    1.16    0.18
GBPUSD          81   0.95   0.67    1.21    0.22
AUDUSD          81   0.94   0.59    1.59    0.13
USDJPY          81   0.95   0.58    2.10    0.13
SPX500USD       80   0.93   0.54    2.51    0.06   <- best calibrated
DE30EUR (DAX)   62   0.87   0.63    3.14    0.16
CN50USD         62   0.94   0.68    4.00    0.21
NAS100USD       62   0.92   0.73    4.79    0.25
XAUUSD (gold)  126   0.87   0.56    6.92    0.08
JP225USD       62   0.92   0.68    7.16    0.20
```
calErr = |cov90 - 0.90| + |cov50 - 0.50| (lower = more honest bands).
pin_bps = mean pinball loss / price, in bps (lower = sharper well-shaped cone).

## Derived verdicts

- Best CALIBRATED (min calErr): SPX500USD (0.06).
- Sharpest cone (min pin_bps): EURUSD (1.16), then GBPUSD (1.21).
- Under-covered 90% band (bands too narrow -> understate risk): XAUUSD and
  DE30EUR (cov90 0.87).
- Over-dispersed 50% band: NAS100USD (0.73), JP225USD (0.68), CN50USD (0.68).

## Honest caveats

- Low pin_bps in FX reflects LOW relative volatility, not superior skill — the
  cone is naturally tighter because the instrument moves less.
- Backfill is historical (non-overlapping) and uses trailing-window GARCH fits
  (walk-forward-ish), robust at n=62-126 but not live forward coverage.
- `crps_bps` is unavailable in this backfill (it predates the CRPS code, tvB14),
  so ranking uses pinball_bps.
