# Block 7 - Regime and serial dependence: block bootstrap and the trend tautology

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how the toolkit was hardened against two remaining honesty gaps - the i.i.d. assumption in its
> bootstraps (which ignores serial dependence) and the trend-following tautology (a trend rule looks
> good only because the sample trends) - via a stationary block bootstrap, a variance-ratio regime
> measure, and a per-regime expectancy split.
>
> Subject version: `analysis/{quant.py,analyze.py,backtest.py}` committed `20afcae` on branch
> `feat/quant-analysis-toolkit` (off `main` c05b8f5). Session 2026-08-05.
>
> Sources: `analysis/quant.py`, `analysis/analyze.py`, `analysis/backtest.py`, `analysis/test_quant.py`
> (local primary source). Preserved run: `sources/probes/regime-blockbootstrap-session-2026-08-05.md`.
> Method: read-only citation of authored code plus a preserved live run over OANDA:XAUUSD 15m. `[CERT]`
> marks a local `file:line`; `[CERT-live]` a preserved live-feed measurement; `[CERT-hw]` a preserved test
> result; `[INFER]` an explicit deduction. METHODOLOGY/DESIGN block: a high `[INFER]`/`[CERT]` ratio is
> expected and healthy.
>
> Refinement layer. Corrects the independence assumption behind [Block 5]'s cones and [Block 6]'s CIs, and
> answers the regime caveat raised in [Block 6] §6.5.

---

## 7.1 - Stationary block bootstrap: resample dependence, not just points `[CERT]`

The i.i.d. bootstrap ([Block 5], [Block 6]) resamples single points, destroying serial structure -
volatility clustering, momentum, mean reversion. `stationary_bootstrap_indices`
(`analysis/quant.py:137`) implements the Politis-Romano scheme: each path continues the current block with
probability `1-p` (`analysis/quant.py:157`) or restarts at a random index with probability `p = 1/L`
(`analysis/quant.py:154`), so blocks have random geometric length with mean `L`. `bootstrap_mean_ci_block`
(`analysis/quant.py:161`) builds a CI from it. `[INFER]` Because it does not pretend neighbours are
independent, the block CI is WIDER - more honest - on autocorrelated data; a test asserts exactly that
widening (`analysis/test_quant.py`, `test_block_ci_wider_than_iid_on_autocorrelated`) `[CERT-hw]`.

## 7.2 - Variance ratio: is there exploitable serial structure? `[CERT]`

`variance_ratio` (`analysis/quant.py:183`) is the Lo-MacKinlay statistic VR(k) = Var(k-bar return) /
(k * Var(1-bar return)), overlapping estimator (`analysis/quant.py:200`). VR ~ 1 is a random walk with no
exploitable structure; VR > 1 is positive serial correlation (trending/momentum); VR < 1 is mean
reversion. A test confirms it separates the three generated regimes `[CERT-hw]`
(`analysis/test_quant.py`, `test_variance_ratio_discriminates_regime`). NOTE: an earlier normalization
carried an extra factor of `k` and read 0.25 on a random walk; the corrected form divides the sample
variance of overlapping k-bar returns by `k * Var_1` directly. `[INFER]`

## 7.3 - Regime classification and the per-regime expectancy split `[CERT]` / `[CERT-live]`

`classify_regime` (`analysis/quant.py:204`) labels each bar `trend-up`, `trend-down`, or `chop` from a
rolling-window regression, trending only when the window R^2 clears the noise floor. `analyze.py` reports
the current regime, the window mix, and VR(2,4,8) (`analysis/analyze.py:124`, `analysis/analyze.py:128`).
`backtest.py` groups each trade by the regime at its ENTRY bar (`analysis/backtest.py:197`,
`analysis/backtest.py:202`) and reports a block-bootstrap CI beside the i.i.d. one
(`analysis/backtest.py:194`). `[INFER]` This is the direct answer to [Block 6]'s tautology warning: it
makes visible whether a trend rule's edge lives only in `trend-up` bars or holds across regimes.

Live evidence on XAUUSD 15m `[CERT-live]` (`sources/probes/regime-blockbootstrap-session-2026-08-05.md`):
the current bar was `chop` despite a trend-heavy window mix (trend-up 126 / chop 114 / trend-down 60) and
near-random VR (VR2 1.02, VR4 1.05, VR8 1.08). The `ema_trend` rule's per-regime split - trend-up n=13
(+11 bps), chop n=10 (+12 bps), trend-down n=3 (-11 bps) - showed the apparent edge was NOT confined to
trends, but every bucket was far too thin to conclude, and the block CI ([-6.37, +24.96] bps) sat slightly
wider than the i.i.d. CI ([-5.38, +24.65]) and still straddled zero.

## 7.4 - What is still not solid `[INFER]`

Regime labels and VR on ~300 bars ([Block 1]) are themselves small-sample estimates; the per-regime
buckets here (3-13 trades) prove the point - the split is a lens, not yet a verdict. The block length `L`
is a free parameter (default 10) that trades bias for variance and is not yet tuned per series. These are
honest limitations to close before any regime-conditioned rule is trusted; the standing guardrail from
[Block 5]/[Block 6] is unchanged.

## 7.5 - Connections

- **[Block 5]** - its i.i.d. bootstrap cone is the independence assumption this block relaxes.
- **[Block 6]** - its CI and its §6.5 regime caveat are what 7.1 and 7.3 answer.
- **[Block 4]** - supplies the rolling-regression trend machinery reused by `classify_regime`.
