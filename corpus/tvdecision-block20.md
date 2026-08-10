# Block 20 - Walk-forward rigor: the conformal correction over-fits the 50% band out-of-sample

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> a walk-forward (out-of-sample) check of the conformal correction that ships live since [Block 13]. It
> confirms the 90% correction generalizes but reveals the 50%-band correction OVER-FITS out-of-sample —
> exactly the kind of honesty the in-sample coverage number cannot show.
>
> Subject version: `analysis/forecast.py` committed on branch `feat/quant-analysis-toolkit`. Session
> 2026-08-10.
>
> Sources: `analysis/forecast.py` plus `analysis/test_forecast.py` (local primary source). Preserved run:
> `sources/probes/conformal-walkforward-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session validation run + TDD. `[CERT]`
> marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block.
>
> Rigor layer. Audits [Block 13]'s live correction and finds where it does not hold.

---

## 20.1 - Why in-sample coverage was not enough `[INFER]`

`[INFER]` [Block 13] seeded the live conformal table from the full backfill and measured `cover_adj` on the
SAME records — coverage that is guaranteed by construction on the calibration set, so it cannot reveal
over-fitting. The honest question is whether a delta learned on past records improves coverage on FUTURE
ones. That needs a temporal hold-out.

## 20.2 - The walk-forward check `[CERT]`

`conformal_validate(records, model, band, train_frac)` sorts records by `made_at`, learns the split-conformal
delta on the first `train_frac`, and measures raw vs adjusted coverage on the held-out remainder
(`analysis/forecast.py:387`), exposed as `forecast.py conformal --validate`. `[INFER]` Same delta math as the
live path, but scored on data it never saw — a true generalization test.

## 20.3 - The 90% band generalizes `[CERT-live]`

Over the pooled backfill (train 70% -> test 30%), the 90% correction is stable out-of-sample: small deltas
and test coverage staying near nominal (SPX 0.96->0.96, gold 0.95->0.98, DAX widened toward 1.00)
(`sources/probes/conformal-walkforward-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` The 90% band's
nonconformity is stable enough across regimes that a past delta still helps ahead.

## 20.4 - The 50% band over-fits `[CERT-live]`

The 50% correction is MIXED out-of-sample: it fixes EURUSD (0.69->0.50) but over-tightens AUDUSD
(0.50->0.38), GBPUSD (0.58->0.38) and NAS100 (0.75->0.35) BELOW nominal
(`sources/probes/conformal-walkforward-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` The 50% delta is
estimated on ~30-60 points and goes stale across a volatility-regime shift, so the train-period tightening
is too aggressive for the test period. The in-sample number hid this entirely.

## 20.5 - The honest consequence `[INFER]`

`[INFER]` The [Block 13] live seeding is OPTIMISTIC for the 50% band. Recommended tempering (not yet applied,
it changes live cone behavior): shrink the delta (apply a fraction), switch the 50% band to ACI online
updating, or restrict the live correction to the more-stable 90% band. This is the rigor step doing its job —
finding that a shipped improvement needs qualifying before it is trusted, rather than trusting the flattering
in-sample number.

## 20.6 - Connections

- **[Block 13]** - the live conformal seeding this audits.
- **[Block 12]** - the conformal layer + ACI (the proposed 50%-band fix).
- **[Block 14]** - the same evidence-first "measure before trusting" discipline (GJR rejected).
