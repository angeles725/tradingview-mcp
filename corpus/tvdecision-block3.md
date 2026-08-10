# Block 3 - Rule validation: backtest, risk, and the Replay lesson

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how a candidate rule is validated by an honest backtest with costs, the three traps that fake an
> edge, the risk-free Replay practice loop, and what real-money readiness actually requires.
>
> Subject version: upstream commit `c05b8f5755ed8e64ea242de88ddbf46aa24d56a4`; session 2026-08-04.
>
> Sources: `../src/cli/commands/replay.js`; METHOD scripts (scratchpad, ephemeral) `gold_backtest.py`,
> `gold_grid.py`, `replay_walk.py`; preserved `sources/probes/decision-methodology-session-2026-08-04.md`.
> Method: read-only backtest of bars pulled via the CLI (see [Block 1]) plus read-only Replay walking.
> `[CERT]` means local primary source (`file:line`); `[CERT-hw]` a preserved session fact; `[INFER]` an
> explicit deduction. METHODOLOGY/DESIGN block: a high `[INFER]`/`[CERT]` ratio is expected and healthy.
>
> Validation layer. Connects [Block 1] (data + Replay surface) and [Block 2] (the rule's raw signal).

---

## 3.1 - Backtest method: signal to expectancy `[INFER]`

A rule is validated by turning its signal into a position, executing on the NEXT bar (never the signal
bar), and measuring per-trade outcomes: expectancy per trade, win rate, max drawdown, and Sharpe, all
after subtracting a transaction cost per position change (`gold_backtest.py` lines 22-54, method
evidence; cost fixed at 0.02% per change / 0.04% round trip, `gold_backtest.py` line 14). Expectancy per
trade is the deciding number - positive is an edge, negative loses - and next-bar execution is what stops
the backtest from cheating on information it would not have had live.

## 3.2 - The three traps that fake an edge `[INFER]`

1. **Tiny sample.** A handful of trades cannot be significant; below ~30 trades the result can be pure
   luck. The backtest prints the trade count and warns explicitly when it is small
   (`gold_backtest.py` lines 66-79, method evidence).
2. **Overfitting.** Parameters chosen after seeing the results are not a discovery. Sweeping an EMA
   parameter grid over the same series shows the "best" pair changes with the parameters - a warning
   sign, not a finding (`gold_grid.py` lines 19-38, method evidence).
3. **Costs.** More trades means more cost; the same grid shows transaction costs eroding, and often
   erasing, a gross edge (`gold_grid.py` lines 31-38, method evidence). A rule that only wins gross is
   not a rule.

## 3.3 - Replay for risk-free practice `[CERT]`

Bar Replay is driven read-only: `replay start` optionally at a date (`../src/cli/commands/replay.js:11`,
`../src/cli/commands/replay.js:16`), `replay step` to advance one bar (`../src/cli/commands/replay.js:18`),
`replay autoplay` to auto-advance (`../src/cli/commands/replay.js:30`), `replay status` to inspect state
(`../src/cli/commands/replay.js:26`), and `replay stop` to return to realtime
(`../src/cli/commands/replay.js:22`). The `replay_walk.py` method script steps Replay bar-by-bar and
records only what a rule WOULD have done - no money is moved. Simulated position mutation
(`replay trade`) is a separate capability, disabled by default (`../src/cli/commands/replay.js:37`).

## 3.4 - The Replay lesson `[INFER]`

Walking a trend-following rule through Replay shows its real shape: it loses small repeatedly in chop and
wins big in sustained trends, so its profitability lives in a few large moves, not a high win rate
(`replay_walk.py`, method evidence). The corollary corrects a common error: a high ("overbought") RSI is
NOT a sell signal in a strong up-trend - price can stay overbought for the whole move. Practice reveals
this in a way a static indicator reading hides.

## 3.5 - Real-money readiness and the isolation limit `[INFER]` / `[CERT]`

Readiness for real money is an honest backtest over enough data PLUS risk management - position sizing
and stop-loss - and specifically NOT a better predictor `[INFER]`. Prediction is capped (see [Block 2]);
survival is a function of sizing and stops. One hard boundary: this tool cannot prove broker or demo
isolation - Replay mode is not evidence that a live broker is disconnected `[CERT]`
(`tradingview-block3.md`; the capability-hardening focus documents that `replay trade` is default-denied
and that broker isolation must be confirmed out of band).

## 3.6 - Connections

- **[Block 1]** - supplies the bars and the Replay command surface used here.
- **[Block 2]** - the raw rule signal (e.g. price-vs-EMA) whose edge this block accepts or refutes.
- **[Block 3 of the capability-hardening focus]** (`tradingview-block3.md`) - the broker-isolation limit
  cited in 3.5.
