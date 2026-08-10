# Preserved session — periodic cadence + multi-TF annotation (2026-08-10)

Live receipts for tvdecision Block 17. Gold OANDA:XAUUSD over CDP + TDD.
Commit f1f8f85.

## 1. Multi-TF check (1m/15m/1h/1D/1M): RSI + EMA500

All five TFs return data (ohlcv caps at ~300 bars -> EMA500 read from the chart
indicator, set to length 500 via `indicator set <id> --inputs {"in_0":500}`):
```
TF     RSI(14)   EMA500     price vs EMA500 (gold ~4390)
1m     46.9      4362       slightly above
15m    72.5      4242       above
1h     81.5      4087       well above (OVERBOUGHT)
1D     67.7      3767       far above
1M     63.2      1227       massively above
```
Price above EMA500 on ALL TFs = multi-scale uptrend; overbought intraday.

## 2. Support/resistance (pivot k=4) and drawings

```
TF   support   resistance
15m  4334.6    4395.4
1h   4316.7    4395.4
1D   4366      4550
1M   1810      5602
```
Drawn as horizontal lines (draw shape needs --price AND --time): Resistencia 4395.4,
Soporte 15m 4334.6, Soporte 1h 4316.7. Later added the periodic SL/TP levels on the
Daily chart. Layout saved via Ctrl+S (active "Sin nombre" layout, 15m).

## 3. Periodic forecasts (cone SL/TP), gold Daily

```
MONTH  h=22  entry=4391.26  p_up=0.501  cone P5=3897.35 P95=4952.80
       STOP-LOSS 3897.35 (-11.25%)  TAKE-PROFIT 4952.80 (+12.79%)  R:R=1.14
WEEK   h=5   entry=4391.26  p_up=0.500  cone P5=4143.22 P95=4651.68
       STOP-LOSS 4143.22 (-5.65%)   TAKE-PROFIT 4651.68 (+5.93%)   R:R=1.05
```
p_up ~ 0.50 and R:R ~ 1.1: the cone is near-symmetric, so SL/TP are risk levels,
not a directional call. Records append to corpus/periodic.jsonl (2 so far).

## 4. HTML report + hook

`periodic_report.py` rendered corpus/periodic-report.html (self-contained,
theme-aware, inline-SVG cone bars) = 4831 bytes, 2 forecasts.
`periodic-hook.sh --force` gates: one monthly run per calendar month, one weekly
run every Monday (ISO week), local-CDP only. Wired in .claude/settings.json
alongside collect-hook (SessionStart + Stop).

## 5. Tests

Full suite 114 green (+5 over 109): trade_levels x2, periodic build/horizon/review x3.
