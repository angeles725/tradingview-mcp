# Preserved session — ACI wired then rejected on walk-forward (2026-08-11)

Live receipt for tvdecision Block 22. Branch `feat/quant-analysis-toolkit`.
`make test` → 127 passed (scipy venv). ACI machinery kept, shipped OFF by default.

## 1. What was wired

`aci_adapted_level(records, model, band, gamma=0.05)` replays ACI (Gibbs-Candes
2021) over a group's scored records in made_at order and returns the adapted
coverage level `1 - alpha_T` (clamped [0.5, 0.999]). `conformalize_band(...,
adaptive=True)` takes the split-conformal delta at that adapted level instead of
the fixed nominal level and reports `aci_level` + `static_delta_frac`.
`conformal_report(..., adaptive=...)` threads it. analyze.py reads `delta_frac`
unchanged, so the live cone would inherit the update automatically.

In-sample the adaptation looked right — DE30 (under-covering 0.87, plus the
+2.17% gap miss) widened to aci_level 0.97 / delta +18.6 bps vs +2.7 static;
over-covering GBP/USDJPY/CN50 tightened. That is the flattering in-sample view.

## 2. The walk-forward check (train 70% -> test 30%, pooled live + backfill)

Mean OOS cover90 across the 10 symbol groups (target 0.90):

```
              mean OOS cover90   |error to 0.90|
raw (none)         0.937             0.044
static conformal   0.917             0.067
ACI                0.842             0.129   <- worst
```

Per-symbol ACI over-tightened the over-coverers BELOW nominal out-of-sample:
AUDUSD 0.86->0.62, EURUSD 0.89->0.79, GBPUSD 0.79->0.71, SPX 0.93->0.75,
USDJPY 0.96->0.79. DE30 0.95 and gold 1.00 held, but the average is dragged down.

## 3. Decision

ACI does NOT generalize out-of-sample — it makes coverage worse than both the
static correction and doing nothing. Same failure class as the B20 50%-band
over-fit: a gamma-step adaptation tuned to the train regime over-corrects the
test regime. Shipped OFF (`conformal_report(adaptive=False)` default); the static
table is regenerated and remains live. Machinery kept for future regime-aware work
that would need a proper online guarantee, not this naive replay.
