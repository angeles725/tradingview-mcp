# Preserved session — multi-market forecast expansion (2026-08-10)

Live, in-session receipts for tvdecision Block 11. Driven over CDP directly
(`node src/cli/index.js` against TradingView Desktop on `127.0.0.1:9222`), NOT
via the MCP server. Wall-clock at capture: 2026-08-10 16:24 UTC (Mon),
unix ~1786379096.

## 1. CDP reachable — TradingView Desktop open

```
$ curl -s http://127.0.0.1:9222/json/version
"Browser": "Chrome/140.0.7339.133",
"User-Agent": "... TradingView/3.3.0 ... Electron/38.2.2 TVDesktop/3.3.0"
```

## 2. Symbol resolution per market (REST search over CDP)

| Market   | Chosen symbol      | Type            | Continuity                     |
|----------|--------------------|-----------------|--------------------------------|
| China    | OANDA:CN50USD      | index CFD       | near-24h continuous            |
| Europe   | OANDA:DE30EUR      | index CFD (DAX) | near-24h continuous            |
| US-tech  | OANDA:NAS100USD    | index CFD       | near-24h continuous            |
| Japan    | OANDA:JP225USD     | index CFD       | near-24h continuous            |
| Korea    | KRX:KOSPI          | cash index      | session-only (09:00-15:30 KST) |

## 3. Intraday OHLCV availability (6-bar summary probe, 15m)

All five resolved and returned 15m bars. Continuity read from `period.to`:

```
OANDA:CN50USD    period.to = 1786378500   (fresh, ~now)      close 15022.7
OANDA:DE30EUR    period.to = 1786378500   (fresh, ~now)      close 26351.8
OANDA:NAS100USD  period.to = 1786378500   (fresh, ~now)      close 29729.9
OANDA:JP225USD   period.to = 1786378500   (fresh, ~now)      close 66883.8
KRX:KOSPI        period.to = 1786343400   (STALE ~9.75h)     close 6299.66  volume=0
```

KOSPI: `volume` field is 0 on every bar (TradingView serves no volume for the
cash index) and the newest bar is ~9.75 h old (Korean session closed).

## 4. Five forecasts recorded (analyze.py --json | forecast.py record)

```
recorded OANDA:CN50USD   15m h=4 S0=15022.70 target_unix=1786382100
recorded OANDA:DE30EUR   15m h=4 S0=26345.20 target_unix=1786382100
recorded OANDA:NAS100USD 15m h=4 S0=29713.20 target_unix=1786382100
recorded OANDA:JP225USD  15m h=4 S0=66871.30 target_unix=1786382100
recorded KRX:KOSPI       15m h=4 S0=6299.66  target_unix=1786347000
store: 46 -> 51 lines
```

The four CFD targets (1786382100) are in the FUTURE relative to capture time
(~1786379096). KOSPI's target (1786347000) is already in the PAST — because it
was projected 4 bars past a STALE last bar (1786343400 + 4*900 = 1786347000),
which lands inside the Korean overnight gap.

## 5. Scoring pass — KOSPI orphan confirmed, no mis-score

```
$ forecast.py score --store analysis/data
scored 0 newly-matured forecast(s) from store analysis/data
```

KOSPI did NOT mis-score against its stale last bar. `nearest_close` tol is
`bar_step_sec // 2 = 450 s`; the distance from target (1786347000) to the newest
KOSPI store bar (1786343400) is 3600 s > 450, so no bar matches. The record
stays pending — and will NEVER mature, because no bar will ever print at a
timestamp inside the overnight gap.

## 6. Data-quality finding — dual gold symbol in the store

```
OANDA:XAUUSD   n=19  scored=6
XAUUSD         n= 7  scored=3     <- bare, pre-prefix-convention records
(other symbols n=1..4, scored=0 — not yet matured)
```

`forecast.py stats` with no `--symbol` reports 9/26 = the two gold keys summed
(6+3 scored / 19+7 total): same instrument fragmented across two symbol keys.
The bare `XAUUSD` records predate the `OANDA:`-prefix convention; scoring is
symbol-exact so they do not cross-contaminate, but calibration for gold is split.
