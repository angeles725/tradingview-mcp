# Block 18 - Confluence: Fibonacci, accumulation, candles, and bull/base/bear panoramas

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> a confluence read that combines Fibonacci retracements (up + down), RSI, EMA trend, accumulation (OBV +
> volume-profile point-of-control), and candle balance into bull / base / bear scenarios — descriptive levels
> the cone is read against, not a prediction.
>
> Subject version: `analysis/quant.py`, `analysis/confluence.py` committed `1c371d3` on branch
> `feat/quant-analysis-toolkit`. Session 2026-08-10.
>
> Sources: the files above plus `analysis/test_quant.py` (local primary source). Preserved run:
> `sources/probes/confluence-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session live run + TDD. `[CERT]` marks a
> local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block.
>
> Context layer. Adds descriptive structure (levels, flow, candles) around [Block 12]'s cone.

---

## 18.1 - Fibonacci both ways `[CERT]`

`fib_levels(low, high, direction)` returns the retracement grid: 'up' measures DOWN from the high
(supports on a pullback of an up-leg), 'down' measures UP from the low (resistances on a bounce)
(`analysis/quant.py:774`). `[INFER]` The two directions are the "fibo alcista / fibo bajista" pair — the same
swing read as support scaffolding or resistance ceiling depending on which way price is retracing.

## 18.2 - Accumulation: OBV flow + volume POC `[CERT]`

`obv` cumulates signed volume — rising = accumulation, falling = distribution (`analysis/quant.py:792`) — and
`volume_profile_poc` finds the price bin that traded the most volume, the point of control / main
accumulation zone (`analysis/quant.py:808`). `[INFER]` Together they answer "acumulaciones": OBV gives the
direction of flow, POC gives the price where it concentrated.

## 18.3 - Combining it into panoramas `[CERT]`

`confluence.analyze` layers the swing, both fib grids, RSI state, EMA50/200 trend, OBV flow, POC, and a
20-candle bull/bear balance, then emits bull / base / bear scenarios keyed off the nearest fib support and
resistance (`analysis/confluence.py:25`, `analysis/confluence.py:78`). `[INFER]` The scenarios are conditional
("hold above X -> target Y; lose X -> below"), never a directional call — they map the terrain, and the
p_up~0.50 cone is still the honest probability.

## 18.4 - What the confluence showed on gold `[CERT-live]`

Gold Daily: price 4390 in an up-trend (above EMA200 4237), RSI 67.7, ACCUMULATION (OBV rising), POC 4079,
13/7 bull candles. The fib grid put price between the 61.8% support (4145) and 50% resistance (4423)
(`sources/probes/confluence-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` The load-bearing find: the fib
0.618 (4145.10) COINCIDES with the [Block 17] weekly stop-loss (4143.22) — an independent double-confirmation
of that support, which is exactly what "combinar todo" is for: two methods pointing at one level.

## 18.5 - The honest frame `[INFER]`

`[INFER]` Fibonacci, S/R, and POC are DESCRIPTIVE (where price turned or traded before), not predictive; RSI
and candle balance are state, not signal. They enrich the read but do not change the cone's ~0.50 direction
([Block 5]). Confluence raises CONFIDENCE IN A LEVEL when independent methods agree, not confidence in a
direction.

## 18.6 - Connections

- **[Block 12]** - the cone these levels are read against.
- **[Block 17]** - the weekly SL (4143) the fib 0.618 confirms; the chart they share.
- **[Block 15]** - the pivot support/resistance the fib grid stacks with.
- **[Block 5]** - the direction-is-~0.50 stance the panoramas respect.
