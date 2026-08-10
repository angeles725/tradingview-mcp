# Block 5 - Honest probability algorithms: fat-tail cones, conditional rigor, and the lookahead trap

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how the probability layer was upgraded from a single Gaussian cone and raw hit-rates to fat-tail Monte
> Carlo, conditional probabilities carrying confidence, and a fixed lookahead-leakage bug with a
> regression guard.
>
> Subject version: working tree of `/home/cristian/TRADINGVIEW` at base commit `35ed7e9`
> (branch `feat/harden-dangerous-capabilities`) with the NEW `analysis/` toolkit added this session
> (uncommitted at capture time). Session 2026-08-05.
>
> Sources: `analysis/quant.py`, `analysis/analyze.py`, `analysis/test_analyze.py` (local primary source).
> Preserved run: `sources/probes/analysis-toolkit-session-2026-08-05.md`.
> Method: read-only citation of authored code plus a preserved live run and test outputs. `[CERT]` marks a
> local `file:line`; `[CERT-live]` a preserved live-feed measurement; `[CERT-hw]` a preserved test result;
> `[INFER]` an explicit deduction. METHODOLOGY/DESIGN block: a high `[INFER]`/`[CERT]` ratio is expected.
>
> Analysis layer. Upgrades the Monte Carlo and empirical-probability portions of [Block 2]; consumes the
> volatility from [Block 4].

---

## 5.1 - Three tail models, because Gaussian understates tail risk `[CERT]`

[Block 2] ran one zero-drift Gaussian cone. The toolkit runs three cones side by side so tail risk is
visible, not assumed: **Gaussian** (`analysis/quant.py:243`), the assumption-free baseline;
**bootstrap** (`analysis/quant.py:254`), which resamples the ACTUAL historical log returns with
replacement and therefore inherits the real fat tails and skew with no distributional assumption; and
**Student-t** (`analysis/quant.py:272`), a parametric fat-tail fit whose degrees-of-freedom estimate the
tail heaviness (`analysis/quant.py:284`, the `stats.t.fit`). All three run zero-drift, so P(up) ~ 0.50 by
construction - no directional bet is injected. `[INFER]` When the bootstrap or Student-t band is wider than
the Gaussian, the series has fat tails and position size must come down; the Gaussian alone would price the
same P5..P95 too narrowly and hide that risk.

The live run made the point concrete on gold: the Student-t fit returned df=2.1 (very heavy tails) and its
P5..P95 band was materially wider than the Gaussian's (P5 4196.8 vs 4217.7; P95 4299.0 vs 4276.6)
`[CERT-live]` (`sources/probes/analysis-toolkit-session-2026-08-05.md`). A Gaussian-only cone would have
understated the downside by ~20 points at P5.

## 5.2 - Conditional probabilities now carry confidence, not just a rate `[CERT]`

[Block 2] counted next-bar hit-rates and printed `n` beside each. The toolkit adds the inference the raw
rate lacks: `conditional_next_up` (`analysis/quant.py:330`) attaches a **Wilson score 95% interval**
(`analysis/quant.py:300`) and a **binomial test** p-value against the unconditional baseline, and it
verdicts each condition. A bucket is `thin-sample` when `n < min_n` (default 30, `analysis/quant.py:350`),
`edge` only when the CI clears the baseline, else `no-edge`. `[INFER]` The Wilson interval is chosen over
the normal-approximation SE precisely because it behaves at small n and near 0/1 - the regime that traps
pattern statistics; a raw rate of 6/8 looks strong until the interval shows it spans almost the whole
[0,1].

## 5.3 - The lookahead trap: statistical rigor does NOT save you from leakage `[CERT]`

The first live run printed a condition "3 up bars in a row" at rate 1.00 on n=54, edge +0.43, p=0.000,
verdict `edge`. A perfect rate on a thick bucket is not a signal - it is **data leakage**. The condition
had been built from `close_{t+1} > close_t`, which IS the prediction target, so the mask contained the
future it claimed to predict. The fix (`analysis/analyze.py:49`): conditions on decision bar `t` may use
only information known at the close of `t`. `up_at[t]` is the move INTO bar t
(`analysis/analyze.py:62`, `close_t > close_{t-1}`, past); the target `target_up` is the move OUT of bar t
(`analysis/analyze.py:58`, `t -> t+1`); the momentum condition now reads `up_at` only
(`analysis/analyze.py:76`). After the fix the same condition reported an honest 0.59 with a CI straddling
baseline -> `no-edge` `[CERT-live]` (`sources/probes/analysis-toolkit-session-2026-08-05.md`).

The load-bearing lesson `[INFER]`: the Wilson interval and the binomial test happily blessed the leaked
condition with `p=0.000`. Statistical machinery cannot detect lookahead; only correct temporal alignment
prevents it. A regression guard now fails the build if any thick bucket hits an implausibly perfect rate on
a random walk (`analysis/test_analyze.py:16`).

## 5.4 - The direction guardrail is unchanged and now enforced in code `[CERT]`

Every probabilistic output remains a range with a probability, never a point. The runner computes the
unconditional baseline as the sample frequency of up bars (`analysis/analyze.py:124`) and prints the
guardrail verbatim at the foot of every report: no line predicts DIRECTION; the methods size the move and
attach a probability; risk management and an honest backtest decide P&L `[CERT-live]`
(`sources/probes/analysis-toolkit-session-2026-08-05.md`). GARCH/EWMA refine the cone WIDTH ([Block 4]),
never the arrow. See [Block 3] for the honest-backtest requirement before any rule is trusted with money.

## 5.5 - Connections

- **[Block 2]** - the prose predecessor; this block replaces its Monte Carlo and empirical-probability
  methods with tested code carrying confidence intervals.
- **[Block 4]** - supplies the clustering-aware sigma the Gaussian cone consumes.
- **[Block 3]** - the backtest/expectancy validation and cost/overfit traps that a `no-edge` verdict here
  feeds into.
