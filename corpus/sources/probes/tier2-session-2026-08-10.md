# Preserved session — Tier 2 refinements (2026-08-10)

Live, in-session receipts for tvdecision Block 14. TDD, scipy venv. Commits
793740b (CRPS + GJR fn + dedupe fix), cfdc3b8 (gold migration).

## 1. CRPS added to the calibration report

`crps_from_quantiles` (2 x trapezoid of the pinball over the stored levels) is a
full-distribution proper score, attached per model in score_record (crps, crps_bps)
and surfaced as mean_crps_bps in the stats table. Unit tests assert non-negativity,
symmetry for a symmetric cone, sharpness (narrower cone -> lower CRPS at the median),
and a tail outcome costing more than a central one.

## 2. Latent dedupe bug found and fixed

`_dedupe` was last-wins and could drop a SCORED record in favour of an unscored
duplicate of the same (symbol,tf,made_at,horizon) key. Because calibration()
dedupes on every read, it was silently losing realized outcomes when duplicates
existed. Discovered while migrating the gold key: the first migration (buggy
dedupe) took 33 scored -> 29 with real loss. Fixed to PREFER scored copies; the
log was restored from git and re-migrated. Unit test asserts a scored copy
survives regardless of order.

## 3. Gold key unified

```
migrated 7 bare 'XAUUSD' -> 'OANDA:XAUUSD'; 81 -> 51 after scored-preferring dedupe; 29 scored
final: 51 records, 29 scored | bare XAUUSD=0 | OANDA:XAUUSD=16
```
The 81->51 collapse is exact-duplicate forecasts (same key) removed by dedupe, not
lost data: every unique key that had a scored copy kept it (29 scored preserved).

## 4. GJR-GARCH A/B — NOT adopted

778 non-overlapping store windows, symmetric-GARCH blend vs GJR-GARCH blend cone
(scratchpad/gjr_ab.py):
```
POOLED sym n=778 cov90=0.920 cov50=0.620 pin_bps=3.531
POOLED gjr n=778 cov90=0.920 cov50=0.620 pin_bps=3.530
```
Per symbol the pinball delta was within +-0.5% (mostly 0.0%); coverage identical.
The leverage term gives NO measurable cone improvement at this horizon/data, and
the GJR 4-parameter fit is ~3-4x the GARCH cost (the A/B ran ~15 min vs ~2 min).
Decision: keep gjr_garch11_vol() as an available, tested function but DO NOT wire
it into the cone. Evidence-based non-adoption, like the earlier adaptive-vol and
gold-tail investigations.

## 5. Tests

Full suite green: 109 passed (+4 over the previous 105: crps x2, gjr x1,
dedupe-prefers-scored x1).
