# Block 4 - Persistent quant toolkit: upgraded numerical methods

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how the earlier ephemeral analysis scripts were rebuilt as a persistent, tested toolkit under
> `analysis/`, and how each numerical method was hardened - trend with statistical significance and a
> robust cross-check, and a family of volatility estimators that respect OHLC information and volatility
> clustering.
>
> Subject version: working tree of `/home/cristian/TRADINGVIEW` at base commit `35ed7e9`
> (branch `feat/harden-dangerous-capabilities`) with the NEW `analysis/` toolkit added this session
> (uncommitted at capture time). Session 2026-08-05.
>
> Sources: `analysis/quant.py`, `analysis/analyze.py`, `analysis/test_quant.py` (local primary source).
> Preserved run: `sources/probes/analysis-toolkit-session-2026-08-05.md`.
> Method: read-only citation of the toolkit we authored, plus a preserved live run over OANDA:XAUUSD 15m.
> `[CERT]` marks a local `file:line`; `[CERT-live]` a preserved live-feed measurement; `[CERT-hw]` a
> preserved test result; `[INFER]` an explicit deduction. This is a METHODOLOGY/DESIGN block, so a high
> `[INFER]`/`[CERT]` ratio is expected and healthy.
>
> Design/analysis layer. Supersedes the trend and volatility portions of [Block 2] with tested code;
> the probability portions are upgraded in [Block 5].

---

## 4.1 - From ephemeral scripts to a persistent, tested toolkit `[CERT]`

The methods described in [Block 2] lived in throwaway scratch scripts (`gold_probabilistic.py`,
`gold_candles.py`) that were not preserved and were lost. This session rebuilt them as a persistent
directory: pure numerical primitives with no I/O in `analysis/quant.py` (`analysis/quant.py:1`), a stdin
runner in `analysis/analyze.py` (`analysis/analyze.py:1`), and two test files
(`analysis/test_quant.py:1`, `analysis/test_analyze.py:1`). Splitting the math from the I/O is what makes
the methods unit-testable; the previous version could not be tested because it mixed the two. `[INFER]`
The persistence itself is the first improvement: a method you cannot re-run or test is a method you will
re-derive and re-break.

## 4.2 - Trend: significance and a robust cross-check, not just slope+R^2 `[CERT]`

[Block 2] reported the OLS slope and R^2. `ols_trend` (`analysis/quant.py:56`) adds the two things a bare
slope hides: the slope's **t-statistic and 95% confidence interval** (`analysis/quant.py:56` computes the
slope standard error from the residual variance and the t-critical value), and a **Theil-Sen** robust
slope (`analysis/quant.py:90`) - the median of all pairwise slopes, which a single price spike cannot move.
A trend is flagged `significant` only when the CI excludes zero AND R^2 clears the 0.30 noise floor
(`analysis/quant.py:56`, the `significant` field). `[INFER]` OLS alone answers "what is the slope"; the CI
answers "is it distinguishable from zero", and Theil-Sen answers "is it an artifact of one outlier". The
live run corroborated all three agreeing on XAUUSD 15m (OLS +0.59/bar, R^2 0.65, t +23.3, Theil-Sen
+0.47/bar) `[CERT-live]` (`sources/probes/analysis-toolkit-session-2026-08-05.md`).

## 4.3 - Volatility: five estimators, because close-to-close wastes information `[CERT]`

[Block 2] used a single stdev of log returns. The toolkit reports five estimators side by side so the
analyst sees the disagreement rather than trusting one number:

- **close-to-close** (`analysis/quant.py:103`) - the noisy baseline, uses only closes.
- **EWMA(0.94)** (`analysis/quant.py:109`) - the RiskMetrics exponential estimator (an IGARCH); weights
  recent bars so it returns the *current-conditional* sigma and tracks volatility clustering.
- **Parkinson** (`analysis/quant.py:122`) - a high-low range estimator; the `1/(4 ln 2)` factor
  (`analysis/quant.py:131`) is its defining constant. The range carries far more information than the
  close, so the estimate is lower-variance.
- **Garman-Klass** (`analysis/quant.py:135`) - combines the range and the open-close move
  (`analysis/quant.py:145`); the most efficient classic estimator when gapping is small.
- **GARCH(1,1)** (`analysis/quant.py:149`) - a Gaussian-MLE fit (Nelder-Mead over omega/alpha/beta) that,
  unlike EWMA, mean-reverts; returns the one-step-ahead conditional sigma, or `None` when scipy is absent
  or the optimiser fails so callers fall back to EWMA.

## 4.4 - The cone consumes the conditional estimator, scaled by sqrt(horizon) `[CERT]`

The Monte Carlo cone ([Block 5]) is fed the *volatility of now*, not a flat average: the runner picks the
GARCH sigma when it fits, else EWMA (`analysis/analyze.py:110`). Per-bar sigma is scaled to the N-bar
horizon by `sqrt(horizon)` (`analysis/quant.py:194`) - the random-walk scaling that also underlies the
daily-percent figure. `[INFER]` Using a clustering-aware sigma matters most exactly when it disagrees with
the historical average: in a volatility spike the flat estimate is stale and undersizes the cone.

## 4.5 - RSI unchanged: Wilder, matching TradingView `[CERT]`

`rsi_wilder` (`analysis/quant.py:202`) preserves the Wilder formulation from [Block 2] - the smoothing that
matches TradingView's own RSI. A test pins it into the expected band on Wilder's classic rising series
`[CERT-hw]` (`analysis/test_quant.py:19`). RSI remains corroboration only; see [Block 3] for why a high RSI
is not a sell signal in a trend.

## 4.6 - Connections

- **[Block 2]** - the prose predecessor; this block replaces its trend/volatility methods with tested code.
- **[Block 5]** - the probability algorithms (fat-tail cones, conditional-probability rigor, lookahead fix)
  that consume the sigma chosen here.
- **[Block 1]** - supplies the ~300-bar series over the `tv` CLI that these methods consume.
