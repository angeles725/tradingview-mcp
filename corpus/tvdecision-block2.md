# Block 2 - Honest probabilistic analysis: range, not point

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how price action was assessed honestly - objective trend, measured volatility, a Monte Carlo
> probability range, and empirical conditional probabilities - and the guardrail that no method
> reliably predicts direction.
>
> Subject version: upstream commit `c05b8f5755ed8e64ea242de88ddbf46aa24d56a4`; session 2026-08-04.
>
> Sources (METHOD scripts, scratchpad, ephemeral): `gold_probabilistic.py`, `gold_candles.py`.
> Preserved: `sources/probes/decision-methodology-session-2026-08-04.md`.
> Method: read-only analysis of bars pulled via the CLI (see [Block 1]); the analytical claims below are
> deductions about method behaviour and are marked `[INFER]` accordingly. `[CERT-hw]` marks a preserved
> session measurement; `[INFER]` an explicit deduction. This is a METHODOLOGY/DESIGN block, so a high
> `[INFER]`/`[CERT]` ratio is expected and healthy - it does not signal exhausted evidence.
>
> Analysis layer. Connects [Block 1] (data source) and [Block 3] (rule validation).

---

## 2.1 - Objective trend: linear regression, not eyeballing `[INFER]`

Trend is measured by fitting a straight line to the closes and reporting the slope (in price per bar)
together with R^2 (`gold_probabilistic.py` lines 23-30, method evidence). The slope states direction and
pace; R^2 states how much of the movement the line actually explains. A low R^2 (below ~0.3) means the
"trend" is mostly noise around the line and the slope should not be trusted as a signal - the script
labels this case explicitly. Reading the slope without R^2 is the classic mistake this step removes.

## 2.2 - Volatility from log returns `[INFER]`

Per-bar volatility is the standard deviation of log returns; the daily figure scales it by
`sqrt(96)` for 96 fifteen-minute bars per 24h (`gold_probabilistic.py` lines 17-21, method evidence).
Volatility sizes the expected range of movement; it says nothing about direction. It is the input the
Monte Carlo cone needs, and the honest denominator for judging whether a move is large or ordinary.

## 2.3 - Monte Carlo cone = a probability range `[INFER]`

The cone simulates many forward paths from measured volatility and reports percentiles
(P5/P25/P50/P75/P95) over an N-bar horizon (`gold_probabilistic.py` lines 40-48, method evidence). Run
with **zero drift**, it is a pure volatility range centred on the current price: P(up) is ~50% by
construction, which is the most honest default because it injects no directional assumption. Feeding the
tiny measured drift back in barely moves P(up) away from 50%, which is itself the finding - it shows how
weak the directional signal is. The deliverable is the band (for example "90% chance inside P5..P95"),
never the median treated as a prediction.

## 2.4 - Empirical conditional probabilities, with the sample-size caveat `[INFER]`

For each candlestick pattern or RSI condition, the method counts how often the NEXT bar closed up and
compares it against the unconditional baseline P(next bar up) (`gold_candles.py` lines 33-58, method
evidence). A condition is only interesting when its conditional probability departs from the baseline.
The non-negotiable caveat is sample size: with ~300 bars, most pattern buckets have very few
occurrences, and a bucket with n below ~15-30 is noise, not an edge - the script prints n next to every
rate so a thin sample cannot masquerade as a signal.

## 2.5 - RSI corroboration, GARCH scope, and the direction guardrail `[CERT-hw]` / `[INFER]`

The RSI(14) computed by the method is the Wilder formulation, matching TradingView's own RSI within the
same session `[CERT-hw]` (`sources/probes/decision-methodology-session-2026-08-04.md`;
`gold_candles.py` lines 20-31). RSI is used only as corroboration; a high ("overbought") RSI is not a
sell signal on its own - see [Block 3]. GARCH-type models, when used, forecast **volatility**, not
direction `[INFER]` - they refine the cone width, never the arrow. The overarching guardrail: no method
here reliably predicts direction, so every output is delivered as a range with an attached probability,
never a single point price `[INFER]`.

## 2.6 - Connections

- **[Block 1]** - supplies the ~300-bar series these methods consume.
- **[Block 3]** - turns a candidate rule (e.g. price-vs-EMA) into a validated edge, or refutes it; also
  carries the "overbought does not mean sell in a trend" lesson referenced in 2.5.
