# Preserved session — HAR-RV/Yang-Zhang + conformal implementation (2026-08-10)

Live, in-session receipts for tvdecision Block 12. TDD (RED→GREEN), driven with
the scipy venv. Implementation committed `e4e67c3` on branch
`feat/quant-analysis-toolkit`.

## 1. TDD — full suite green after both phases

```
$ <venv>/python -m pytest analysis/ -q
104 passed in ~36s
```
Baseline before the change was 91 passing; +13 new tests (6 in test_quant.py for
the vol upgrade, 7 in test_forecast.py for the conformal layer). Each phase was
confirmed RED (new tests failing with AttributeError) before implementation.

## 2. #1 live — the cone now blends GARCH with HAR-RV (gold, 15m)

```
garman_klass    0.001495
yang_zhang      0.001500
har_rv          0.001288
garch11         0.001637
cone_sigma_used 0.001462     <- blend_sigma(garch, har) = (0.001637+0.001288)/2
```
The HAR-RV forecast (0.001288) is below the GARCH clustering sigma (0.001637), so
the blended cone is slightly tighter than GARCH-only, reflecting the lower
realized-range volatility of the moment.

## 3. #2 loop — conformal correction end-to-end

Real log (no group has enough matured forecasts yet):
```
$ forecast.py conformal --min-n 20
conformal corrections: 0 group(s) (min_n=20)
  (no group has >= min_n scored forecasts yet — keep collecting)
```

Synthetic correction applied through analyze (gold, delta90=0.003):
```
baseline           P5=4331.41 P50=4352.29 P95=4373.25
--conformal        P5=4318.36 P50=4352.29 P95=4386.31   (widened ~13 = 0.003*S0)
conformal_applied= {'gaussian': {'delta90_frac': 0.003, 'delta50_frac': 0.001}}
```
P50 and p_up are untouched; only the band edges move. A missing conformal file is
a safe no-op (`conformal_applied = None`, cone unchanged).

Coverage-guarantee property (unit test, n=20 too-narrow 90% band):
`cover_raw = 0.25 → cover_adj ≥ 0.90` after the split-conformal correction.

## 4. Calibration snapshot at implementation time (PRE-change cone)

`forecast.py` scored 30 gaussian forecasts across all markets (target matured;
the background hook scored them). These used the OLD GARCH-only cone.

```
symbol                n n_eff  cov90  cov50  pin_bps
OANDA:XAUUSD          7     4   1.00   0.86      4.9
OANDA:CN50USD         3     1   1.00   0.33      2.7
OANDA:DE30EUR         3     1   1.00   0.33      2.0
OANDA:JP225USD        3     1   1.00   1.00      4.6
OANDA:NAS100USD       3     1   1.00   1.00      2.7
(FX majors)         1-2     1   0.50-1.00  var    0.9-3.0
----------------------------------------------------
ALL (pooled)         30     4   0.93   0.60      3.0
```
Pooled cov90=0.93 is near the 0.90 nominal, but n_eff is tiny (1 per symbol, 4
pooled) — per-symbol figures are noise. Far below the ~200 matured/quantile the
methods research names for trustworthy tail calibration. The conformal layer
stays dormant until a group reaches min_n=20 scored records.
