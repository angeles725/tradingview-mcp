# Block 12 - HAR-RV/Yang-Zhang cone volatility and the conformal calibration layer

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> two evidence-backed upgrades chosen from a three-agent methods survey and implemented under strict TDD
> — (1) the cone's volatility input now blends the GARCH(1,1) conditional sigma with a HAR-RV forecast over
> a Yang-Zhang / Rogers-Satchell realized-variance series, and (2) a split-conformal calibration layer that
> turns the coverage DIAGNOSTIC into an active band CORRECTION with a finite-sample coverage guarantee.
>
> Subject version: `analysis/quant.py`, `analysis/analyze.py`, `analysis/forecast.py`,
> `analysis/collect-hook.sh` committed `e4e67c3` on branch `feat/quant-analysis-toolkit`. Session 2026-08-10.
>
> Sources: the four files above plus `analysis/test_quant.py` / `analysis/test_forecast.py` (local primary
> source). Preserved run: `sources/probes/har-conformal-impl-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session TDD + live run. `[CERT]` marks a
> local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block.
>
> Numerical layer. Sharpens [Block 5]'s cone (better vol input) and closes [Block 8]'s calibration loop
> (the coverage numbers now correct the cone, not just report on it).

---

## 12.1 - Why these two, and the honest ceiling `[INFER]` / `[CERT-live]`

Three independent web-research agents converged on the same verdict: intraday DIRECTION is ~unpredictable
(p_up~0.50) and the value is in VOLATILITY and CALIBRATION, so the cone architecture is right and the wins
are in its vol input and its coverage layer (`sources/probes/har-conformal-impl-session-2026-08-10.md`)
`[CERT-live]`. `[INFER]` HAR-RV over a range estimator and conformal prediction were the two highest
evidence-to-effort items that map onto components the toolkit already has. The standing ceiling is data:
trustworthy tail calibration needs ~200 matured non-overlapping forecasts per quantile, and the store is at
n_eff~4 — so both upgrades are built and dormant, not yet proven on our own record.

## 12.2 - Rogers-Satchell and Yang-Zhang: gap-robust realized variance `[CERT]`

`rogers_satchell_var` returns a PER-BAR, drift-INDEPENDENT variance proxy (`analysis/quant.py:613`); because
each term is an intraday high/low/close/open combination it is non-negative and never contaminated by an
overnight jump. `yang_zhang_vol` combines the overnight (close->open), open->close and Rogers-Satchell terms
with the standard k weighting into the minimum-variance OHLC sigma that handles gaps correctly
(`analysis/quant.py:624`). `[INFER]` This is exactly the property the cash-index gap problem of [Block 11]
exposed: a vol input that does not blow up across session boundaries.

## 12.3 - HAR-RV: the forecast, made causal `[CERT]`

`har_rv_forecast` fits Corsi's Heterogeneous-AutoRegressive model on the per-bar realized-variance series —
trailing means over three timescales (default 1/5/22) regressed on next-period variance via least squares
(`analysis/quant.py:723`). The design is strictly CAUSAL: the features for target `t` are averages ENDING
BEFORE `t`, and the forward feature uses only bars up to now — no look-ahead (the trap [Block 5] documents).
It falls back to the mean variance when the series is shorter than the longest window and clamps a
degenerate (non-finite or non-positive) fit back to that mean.

## 12.4 - The blended cone sigma `[CERT]` / `[CERT-live]`

`analyze.py` now computes the HAR-RV forecast from the Rogers-Satchell series (`analysis/analyze.py:127`)
and sets the cone sigma to an equal-weight blend of the GARCH(1,1) conditional sigma and that HAR-RV
forecast via `blend_sigma` (`analysis/analyze.py:133`, `analysis/quant.py:754`), falling back to EWMA when
neither fits. Both new estimators are reported alongside the others (`analysis/analyze.py:185`). Live on
gold: GARCH 0.001637 + HAR 0.001288 -> blend 0.001462, a slightly tighter cone reflecting lower realized
range vol (`sources/probes/har-conformal-impl-session-2026-08-10.md`) `[CERT-live]`.

## 12.5 - Conformal: from diagnostic to correction `[CERT]`

`conformal_delta` is the split-conformal radius — the `ceil((n+1)*level)`-th order statistic of the
nonconformity scores, clamped to the max (`analysis/forecast.py:265`) — the finite-sample rule that yields
the `>= level` coverage guarantee. `conformalize_band` computes, per band, the nonconformity
`E = max(lo - y, y - hi) / S0` (return-space, so it is scale-free across a symbol's price) and reports
coverage BEFORE and AFTER applying the correction (`analysis/forecast.py:282`). `aci_next_alpha` is the
Adaptive Conformal Inference online update for non-stationarity (`analysis/forecast.py:315`).
`[CERT-live]` A unit test drives a deliberately too-narrow 90% band from cover_raw 0.25 to cover_adj >= 0.90.

## 12.6 - Applying it, and the closed loop `[CERT]`

`apply_conformal_widening` shifts the 90% (P5/P95) and 50% (P25/P75) band edges out by `delta_frac*S0`,
leaving P50 and p_up untouched and re-sorting so the band stays monotone even under a negative (tightening)
delta (`analysis/forecast.py:326`). `conformal_report` groups corrections by `symbol|tf|horizon`
(`analysis/forecast.py:340`) and a new `conformal` CLI writes the table to `conformal.json`
(`analysis/forecast.py:468`). The hook closes the loop: `analyze` records with `--conformal` pointed at the
table (`analysis/collect-hook.sh:89`, `analysis/collect-hook.sh:55`), and after scoring it refreshes the
table (`analysis/collect-hook.sh:100`). `[INFER]` Ordering matters: a tick records using the PRIOR tick's
table, then re-derives it from freshly matured forecasts for the next tick.

## 12.7 - What is safe today `[CERT-live]` / `[INFER]`

On the real log the `conformal` command reports 0 groups (no `symbol|tf|horizon` has min_n=20 scored yet),
and a missing `conformal.json` makes `analyze --conformal` a no-op with the cone unchanged
(`sources/probes/har-conformal-impl-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` So the layer is wired
but inert until data accumulates — which is the honest state: the coverage snapshot at build time (pooled
cov90~0.93 at n_eff~4) is directionally reassuring but statistically inconclusive, and it reflects the OLD
GARCH-only cone, not the new blend.

## 12.8 - Connections

- **[Block 5]** - the honest cone + the look-ahead trap this HAR design avoids.
- **[Block 8]** - the decision engine whose calibration loop the conformal layer now closes.
- **[Block 10]** - the collection hook extended to refresh and consume `conformal.json`.
- **[Block 11]** - the gap problem that motivated a gap-robust (Rogers-Satchell / Yang-Zhang) vol input.
