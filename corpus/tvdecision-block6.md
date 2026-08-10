# Block 6 - Honest backtest engine: costs, out-of-sample, and independent trades

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how the rule-validation prose of [Block 3] became a tested backtest engine that resists the three ways
> a backtest lies - ignored costs, thin samples, and overfitting - and how a fourth, subtler lie
> (autocorrelated overlapping trades) was found and fixed on live gold.
>
> Subject version: `analysis/backtest.py` committed `91b7efc` on branch `feat/quant-analysis-toolkit`
> (off `main` c05b8f5). Session 2026-08-05.
>
> Sources: `analysis/backtest.py`, `analysis/quant.py`, `analysis/test_backtest.py` (local primary source).
> Preserved run: `sources/probes/backtest-engine-session-2026-08-05.md`.
> Method: read-only citation of authored code plus a preserved live run over OANDA:XAUUSD 15m. `[CERT]`
> marks a local `file:line`; `[CERT-live]` a preserved live-feed measurement; `[CERT-hw]` a preserved test
> result; `[INFER]` an explicit deduction. METHODOLOGY/DESIGN block: a high `[INFER]`/`[CERT]` ratio is
> expected and healthy.
>
> Validation layer. Turns the [Block 4]/[Block 5] toolkit's candidate rules into a validated edge or a
> refutation; it is the code realization of [Block 3].

---

## 6.1 - No lookahead: fill at the next open, never the signal bar `[CERT]`

A signal on bar `t` is filled at the OPEN of bar `t+1` and exited at the open of `t+1+hold`
(`analysis/backtest.py:109`, `analysis/backtest.py:110`). A trade with no room for entry+hold is dropped,
never peeked (`analysis/backtest.py:113` region drops when `exit_i >= n`). `[INFER]` This is the same
alignment discipline that [Block 5] enforces for conditional probabilities: the rule may never see the bar
it trades into. A test pins the fill to `open[t+1] -> open[t+1+hold]` exactly `[CERT-hw]`
(`analysis/test_backtest.py:16`).

## 6.2 - The three liars, subtracted and flagged `[CERT]`

- **Costs.** Transaction cost is subtracted per side as a round-trip in return units
  (`analysis/backtest.py:105`); the report shows gross vs net so the cost drag is explicit. A test
  confirms higher cost monotonically lowers net expectancy `[CERT-hw]` (`analysis/test_backtest.py:38`).
- **Sample.** `compute_stats` flags `thin-sample` below 30 trades and attaches a **bootstrap 95% CI** on
  the mean net return (`analysis/backtest.py:121`; the CI comes from `bootstrap_mean_ci`,
  `analysis/quant.py`), so an edge whose CI includes zero is refused. An `edge` verdict requires the whole
  CI above zero (`analysis/backtest.py:137`).
- **Overfit.** `walk_forward` (`analysis/backtest.py:145`) splits the timeline and reports in-sample vs
  out-of-sample expectancy; an edge that survives only in-sample is overfit. `[INFER]`

## 6.3 - The fourth liar: overlapping trades inflate significance `[CERT]` / `[CERT-live]`

The first live run of a trend rule looked like a clear winner. It was not: with `hold=8` the rule was long
almost continuously, so its "182 trades" were overlapping windows of the SAME position - autocorrelated,
not independent - and the bootstrap CI treated them as i.i.d., overstating significance. The fix makes
non-overlapping trades the DEFAULT: once in a trade, further signals are ignored until it closes
(`analysis/backtest.py:96` documents it; `analysis/backtest.py:107` tracks `busy_until`;
`analysis/backtest.py:113` skips a signal while a position is open). `--overlap` still exposes the raw
signal-conditional view but must never be read as a CI. `[INFER]`

The live contrast is the evidence `[CERT-live]` (`sources/probes/backtest-engine-session-2026-08-05.md`):
on XAUUSD 15m the `ema_trend` rule showed `+13.47 bps/trade`, "edge survives out-of-sample" across 182
OVERLAPPING trades - but collapsed to 26 INDEPENDENT trades with expectancy `+9.14 bps` and a 95% CI of
`[-5.38, +24.65]` straddling zero, verdict `thin-sample`; in-sample it was actually negative (33% win
rate). The overlapping view had manufactured the edge; the honest view refuses to conclude.

## 6.4 - A rule cannot beat a random walk, by construction `[CERT-hw]`

An invariant test asserts that on a pure random walk NO rule yields a significant NET edge
(`analysis/test_backtest.py`, `test_no_free_edge_on_random_walk`). `[INFER]` This is the falsifiability
anchor: if the engine ever prints an `edge` on noise, the engine - not the market - is broken.

## 6.5 - Regime caveat and the standing guardrail `[INFER]`

A trend-following rule showing an edge in a strongly trending sample is nearly tautological; a valid
backtest still says nothing about chop, and the ~300-bar live horizon ([Block 1]) is a small window. The
engine therefore refuses more than it confirms, and the guardrail from [Block 5] stands: a backtest is
necessary, not sufficient; risk management and position sizing decide survival regardless of any measured
edge. Replay practice ([Block 3]) is where a surviving rule earns trust before real money.

## 6.6 - Connections

- **[Block 3]** - the prose predecessor; this block is its tested code realization.
- **[Block 4]/[Block 5]** - supply the rules and the alignment discipline this engine validates.
- **[Block 1]** - the ~300-bar live horizon that bounds how much a backtest here can conclude.
