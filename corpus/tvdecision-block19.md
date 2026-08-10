# Block 19 - The actionable layer: risk-based sizing and price alerts on the confluence levels

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> turning the honest analysis into decisions WITHOUT predicting direction — a fixed-fractional position sizer
> anchored to the confluence stop, and live price alerts at the key levels so the system watches for you.
>
> Subject version: `analysis/forecast.py` and live CDP alerts (`src/cli/commands/alerts.js`) committed
> `c728f32` on branch `feat/quant-analysis-toolkit`. Session 2026-08-10.
>
> Sources: the files above plus `analysis/test_forecast.py` (local primary source). Preserved run:
> `sources/probes/actionable-layer-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session live run + TDD. `[CERT]` marks a
> local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block.
>
> Decision layer. Makes [Block 17]'s SL/TP and [Block 18]'s confluence actionable, still without a
> directional bet.

---

## 19.1 - Sizing from the stop, not from a guess `[CERT]`

`size_for_risk(levels, equity, risk_pct)` risks a fixed fraction of equity and sizes the position so the
distance to the stop equals that cash risk: units = risk_cash / |entry - stop|, plus notional, cash reward
at the take-profit, leverage and R:R; a zero stop-distance returns zero units so it never divides by zero
(`analysis/forecast.py:145`). `[INFER]` The stop comes from `trade_levels` (the cone / confluence, [Block 17]),
so the size is anchored to the forecast's own uncertainty — a wider band automatically means a smaller
position for the same risk.

## 19.2 - What it says in practice `[CERT-live]`

On the weekly gold levels (entry 4391, SL 4143 = Fib 0.618 / weekly stop, TP 4652) a $10,000 account risking
1% takes 0.403 oz ($1,770 notional, 0.18x leverage, +$105 if the TP is hit); at 0.5% it halves
(`sources/probes/actionable-layer-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` This is the concrete
output the user needs: not "buy", but "if you take this, here is exactly how much, and here is the risk".

## 19.3 - Alerts that watch the levels `[CERT]` / `[CERT-live]`

The `alert create --price --condition crossing` command (`src/cli/commands/alerts.js:11`) set four live
alerts at the confluence levels: SL/Fib 0.618 (4143), Fib 0.5 (4423), weekly TP (4652), and the POC/
accumulation zone (4079) (`sources/probes/actionable-layer-session-2026-08-10.md`) `[CERT-live]`. `[INFER]`
Passive monitoring is the honest use of a no-edge-on-direction system: it does not tell you which way price
goes, it tells you WHEN price reaches a level you already decided matters.

## 19.4 - Confluence auto-produced each Monday `[INFER]`

`[INFER]` With the confluence read embedded in the periodic record ([Block 18], [Block 17]) and rendered in
the HTML report, the Monday hook now emits the full picture automatically — cone SL/TP, fibs, RSI,
accumulation, and bull/base/bear panoramas — so the sizer and alerts always have current levels to work from.

## 19.5 - The frame holds `[INFER]`

`[INFER]` Sizing and alerts add ACTION, not prediction. The direction stays ~0.50 ([Block 5]); what these
give is disciplined risk (size by the stop) and attention (alerts at levels). That is the realistic edge of a
retail probabilistic toolkit: lose small when wrong, be present when a level trades — not forecast the future.

## 19.6 - Connections

- **[Block 17]** - the cone SL/TP the sizer anchors to.
- **[Block 18]** - the confluence levels the alerts watch.
- **[Block 8]** - the fixed-risk sizing idea, here tied explicitly to the confluence stop.
- **[Block 5]** - the direction-is-~0.50 stance both the sizer and alerts respect.
