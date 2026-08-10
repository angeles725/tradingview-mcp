# Block 17 - Periodic cadence: monthly + weekly-Monday forecasts with cone stop-loss/take-profit

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> a calendar cadence on top of the cone — one monthly context forecast and one every Monday — each carrying
> cone-derived stop-loss / take-profit and risk measures, plus multi-timeframe chart annotation (RSI,
> EMA500, support/resistance) and an HTML report.
>
> Subject version: `analysis/forecast.py`, `analysis/periodic.py`, `analysis/periodic_report.py`,
> `analysis/periodic-hook.sh` committed `f1f8f85` on branch `feat/quant-analysis-toolkit`. Session 2026-08-10.
>
> Sources: the files above plus `analysis/test_periodic.py` (local primary source). Preserved run:
> `sources/probes/periodic-cadence-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session live run + TDD. `[CERT]` marks a
> local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block.
>
> Cadence layer. Wraps [Block 12]'s cone in a monthly/weekly rhythm with risk levels and a report.

---

## 17.1 - Stop-loss / take-profit from the cone, not a guess `[CERT]`

`trade_levels(cone, side, entry)` derives the stop-loss and take-profit from the cone band itself: long ->
SL at the downside P5, TP at the upside P95 (short mirrored), with entry defaulting to the median P50, and it
returns risk/reward distances, the R:R ratio, and SL/TP distances in % (`analysis/forecast.py:120`).
`[INFER]` This keeps the levels HONEST — they are the forecast's own uncertainty band, so a wider cone
automatically sets wider stops, and R:R falls out of the geometry rather than a round number.

## 17.2 - Two cadences, one shared cone `[CERT]`

`periodic.py` runs a monthly forecast (horizon ~22 daily bars) and a weekly-Monday forecast (~5 daily bars),
with the horizon table keyed by period and timeframe (`analysis/periodic.py:37`) and the cone built through
the SAME `quant.cone_sigma` recipe as the live path so the periodic cone cannot drift
(`analysis/periodic.py:43`, `analysis/periodic.py:78`). `[INFER]` One recipe, three callers (analyze,
backfill, periodic) — the anti-drift discipline of [Block 13] extended to the cadence.

## 17.3 - The weekly review carries the month `[CERT]`

The Monday forecast reads the most recent prior weekly record for the symbol and reports whether last week's
move landed in its cone (`analysis/periodic.py:59`), so each week is scored against what it actually
predicted while the monthly forecast supplies the wider context. `[INFER]` This is the "se vio la semana
pasada / se viene trabajando el mes" loop: review the prior week, forecast the next, inside the month's band.

## 17.4 - Live levels, gold `[CERT-live]`

On gold Daily the monthly cone gave SL 3897.35 (-11.25%) / TP 4952.80 (+12.79%), R:R 1.14; the weekly gave
SL 4143.22 (-5.65%) / TP 4651.68 (+5.93%), R:R 1.05 (`sources/probes/periodic-cadence-session-2026-08-10.md`)
`[CERT-live]`. `[INFER]` p_up ~ 0.50 and R:R ~ 1.1 confirm the cone is near-symmetric: the levels are risk
management, not a buy/sell signal — consistent with the whole toolkit's stance.

## 17.5 - Report and calendar-gated hook `[CERT]`

`periodic_report.py` renders a self-contained, theme-aware HTML report of the month's forecasts with an
inline-SVG cone bar per card (`analysis/periodic_report.py:86`, `analysis/periodic_report.py:41`).
`periodic-hook.sh` fires at most once per calendar month and once each Monday per ISO week
(`analysis/periodic-hook.sh:33`, `analysis/periodic-hook.sh:41`) over the recommended instruments
(`analysis/periodic-hook.sh:18`). `[INFER]` A local hook, not cloud cron, because the forecast needs the
local TradingView chart over CDP — the same constraint [Block 10] hit.

## 17.6 - Multi-TF annotation `[CERT-live]`

Across 1m/15m/1h/1D/1M gold sits above EMA500 on every TF (multi-scale uptrend) yet is overbought intraday
(1h RSI 81.5); support/resistance by pivot were drawn on the chart, and the layout saved
(`sources/probes/periodic-cadence-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` Support/resistance are
descriptive (where price turned before), not predictive — annotation to read the cone against, not a signal.

## 17.7 - Connections

- **[Block 12]** - the cone the SL/TP and cadence wrap.
- **[Block 13]** - the shared `cone_sigma` recipe reused so the periodic cone matches live.
- **[Block 15]** - the recommended instruments the hook forecasts.
- **[Block 10]** - the local-CDP hook pattern this cadence follows.
