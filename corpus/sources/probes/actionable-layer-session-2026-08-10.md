# Preserved session — actionable risk layer: sizer + alerts (2026-08-10)

Live receipt for tvdecision Block 19. Gold OANDA:XAUUSD over CDP + TDD.
Commit c728f32.

## 1. Risk-based position sizer (from the confluence stop)

`size_for_risk(levels, equity, risk_pct)` on the weekly gold levels
(entry 4391.26, SL 4143.22 = Fib 0.618 / weekly stop, TP 4651.68):
```
equity $10,000  risk 1.0%  -> risk $100  | 0.403 oz | notional $1,770 | 0.18x | TP +$105 (R:R 1.05)
equity $10,000  risk 0.5%  -> risk $50   | 0.202 oz | notional $885   | 0.09x | TP +$52  (R:R 1.05)
equity $50,000  risk 1.0%  -> risk $500  | 2.016 oz | notional $8,852 | 0.18x | TP +$525 (R:R 1.05)
```
units = risk_cash / stop-distance; zero stop-distance -> zero units (safe).

## 2. Live price alerts at the confluence levels

```
alert create --price 4143.22 --condition crossing -m "SL semana / Fib 0.618 (soporte doble)"  -> alert_id 5341516408
alert create --price 4423.32 --condition crossing -m "Resistencia / Fib 0.5"
alert create --price 4651.68 --condition crossing -m "TP semana"
alert create --price 4079.47 --condition crossing -m "POC / zona de acumulacion"
```
alert list confirmed all four. The system now watches the levels and notifies on a
crossing — passive monitoring, no prediction.

## 3. Confluence embedded in the periodic report

periodic.build now embeds the confluence read; periodic_report renders a
Confluencia section (fibs / RSI / accumulation / bull-base-bear panoramas) per
card, so the Monday hook produces it automatically. corpus/periodic-report.html
regenerated (10 forecasts, 6 confluence sections).

## 4. Tests

Full suite 120 green (+2 sizer over the 118 with confluence-embed).
