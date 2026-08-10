# Preserved session — confluence analysis (2026-08-10)

Live receipt for tvdecision Block 18. Gold OANDA:XAUUSD Daily over CDP + TDD.
Commit 1c371d3.

## Confluence output (gold, Daily, 300 bars)

```
CONFLUENCE  OANDA:XAUUSD  D   price=4390.20   trend=up
swing: low 3244.41 -> high 5602.23 (leg up)
RSI 67.7 (neutral) | flow: accumulation (OBV slope +5,903,955) | POC 4079.47
candles(20): 13 bull / 7 bear, last bull
EMA50 4202.31 | EMA200 4237.25
FIBO ALCISTA (supports):  0.382:4701.54  0.5:4423.32  0.618:4145.10  0.786:3748.99
FIBO BAJISTA (resist.):   0.382:4145.10  0.5:4423.32  0.618:4701.54  0.786:5097.65
nearest: support 4145.10 | resistance 4423.32
PANORAMAS:
  ALCISTA: hold above fib 4145.10 + POC 4079.47 -> target 4423.32 (favoured: trend up + accumulation)
  BASE:    chop 4145.10..4423.32
  BAJISTA: lose 4145.10 -> next fib/POC below (less likely while accumulation holds)
```

## Key confluence found (drawn on Daily)

- Fib 0.618 = 4145.10 COINCIDES with the weekly stop-loss 4143.22 (Block 17) -> a
  doubly-confirmed support zone.
- Price 4390 sits at Resistencia 4395 (Block 15/pivots) and just under Fib 0.5 (4423).
- POC / accumulation 4079 sits below, near the monthly SL 3897 / Fib 0.786 (3749) zone.

Drawn: Fib grid 0.382/0.5/0.618/0.786 (orange) + POC 4079 (purple) on top of the
existing S/R, periodic SL/TP, EMA500 and RSI. Screenshot captured.

## Tests

Full suite 117 green (+3 over 114): fib_levels, obv, volume_profile_poc.
