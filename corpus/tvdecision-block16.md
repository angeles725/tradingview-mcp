# Block 16 - The capability boundary: analysis works, execution and order-flow do not

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> where the toolkit's reach ends. A full replay-loop demo (forecast -> decide -> order) plus probes of the
> order-book and streaming tools establish that the ANALYSIS half is wired end-to-end while EXECUTION
> (even paper) and the order-flow directional edge are not accessible with this setup.
>
> Subject version: `analysis/decide.py`, `src/cli/commands/replay.js`, `src/cli/commands/data.js`,
> `src/core/data.js` on branch `feat/quant-analysis-toolkit`. Session 2026-08-10.
>
> Sources: the files above (local primary source). Preserved run:
> `sources/probes/capability-boundary-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session replay demo and CDP probes.
> `[CERT]` marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit
> deduction. METHODOLOGY/DESIGN block.
>
> Boundary layer. Marks what NOT to promise: the honest edge of the CDP toolkit.

---

## 16.1 - The analysis half runs end-to-end `[CERT]` / `[CERT-live]`

In replay (SPX500USD, Daily, cursor 2026-06-02) the loop forecast -> decide ran cleanly: a cone from the
bars up to the cursor, then `decide.py`, whose default stance is NO-TRADE and which trades only when EVERY
gate passes (`analysis/decide.py:12`, `analysis/decide.py:82`). It returned NO-TRADE, failing Gate A
because the trend was not momentum-confirmed (VR4=0.63, z=-1.53) (`analysis/decide.py:102`,
`analysis/decide.py:112`; `sources/probes/capability-boundary-session-2026-08-10.md`) `[CERT-live]`.
`[INFER]` This is the system working as designed: p_up~0.498, no edge, so it correctly declines. The honest
value is the gate that says "wait", not a trigger.

## 16.2 - Replay stepping works; the paper ORDER does not `[CERT]` / `[CERT-live]`

`replay step` advanced the cursor ~4 days across four calls (`src/cli/commands/replay.js:16`). But
`replay trade buy|close` (`src/cli/commands/replay.js:37`) returned `success:true` with `position: null`
and `realized_pnl: null` throughout — the order never registered a position, though the replay-trading UI
labels exist (`sources/probes/capability-boundary-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` The
command clicks but no position surfaces: paper-order EXECUTION is not functional here, consistent with the
broker-isolation boundary of [Block 3]. There is also no real-broker order command at all — only
`replay trade` (simulation) and `data trades` (read-only).

## 16.3 - Order-book depth is inaccessible `[CERT]` / `[CERT-live]`

`data depth` (`src/cli/commands/data.js:76`) looks for a DOM panel and errors when absent
(`src/core/data.js:460`); on OANDA:XAUUSD it returned "DOM / Depth of Market panel not found."
(`sources/probes/capability-boundary-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` OANDA CFDs expose no
L2 book, so the ONE documented source of genuine short-horizon directional edge (order-flow imbalance, from
the methods research) is out of reach without a paid L2/futures feed and an open DOM panel.

## 16.4 - Streaming works but is non-additive `[CERT-live]` / `[INFER]`

`stream bars` emits JSONL bar updates on price change (`sources/probes/capability-boundary-session-2026-08-10.md`)
`[CERT-live]`. `[INFER]` It does NOT move the binding constraint: the 30-min hook's 300-bar pulls already
capture every closed bar (no gaps), and the independent-sample count grows with wall-clock, not poll
frequency (h=4 non-overlapping = ~1 independent forecast/hour/instrument, [Block 12] `_independent_subset`).
Streaming would only reduce scoring latency — marginal — so it was not adopted.

## 16.5 - What this bounds `[INFER]`

`[INFER]` The toolkit is an honest ANALYST, not a TRADER: it forecasts calibrated bands and gates a
BUY/SELL/NO-TRADE decision, but it cannot place orders (real or paper) and cannot see order flow. Given the
p_up~0.50 evidence ([Block 5], [Block 15]), that boundary is not a loss — the value was never in pulling the
trigger. The next real levers stay on the analysis side: accumulating live calibration and letting the
[Block 13] conformal correction refine, not wiring execution.

## 16.6 - Connections

- **[Block 3]** - the broker-isolation limit this demo confirms.
- **[Block 8]** - the gated decision engine that correctly returned NO-TRADE.
- **[Block 5]** / **[Block 15]** - the p_up~0.50 evidence that makes the execution gap unimportant.
- **[Block 12]** / **[Block 13]** - the calibration + conformal levers that remain the real improvements.
