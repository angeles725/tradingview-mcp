# Preserved session — CDP execution & live-data capability boundary (2026-08-10)

Live receipts for tvdecision Block 16. Driven over CDP (`node src/cli/index.js`,
port 9222). Chart restored to OANDA:XAUUSD 15m realtime afterwards.

## 1. Replay full-loop demo (SPX500USD, Daily, cursor 2026-06-02)

Date-seeked replay FAILED on 15m ("date may not have data for this timeframe" on
SPX 15m for 2026-06/07); succeeded on Daily.

Forecast at the replay cursor:
```
analyze.py --tf D --horizon 4 -> S0=7588.8  next-4d cone P5=7428.8 P50=7588.5 P95=7751.4  p_up=0.498  regime=trend-up
```
Decision:
```
decide.py -> NO-TRADE  [none]  no defensible direction (Gate A)
  [FAIL] A_direction  trend sig (R^2=0.79), regime=trend-up, VR4=0.63 (z=-1.53)
  "No order was placed. Validate on Replay/paper before ever risking real money."
```
Stepping: `replay step` x4 advanced current_date 1780358399 -> 1780693199 (~4 days). WORKS.

EXECUTION GAP:
```
replay trade buy   -> {"success": true, "action": "buy",   "position": null, "realized_pnl": null}
replay trade close -> {"success": true, "action": "close", "position": null, "realized_pnl": null}
replay status      -> position: null, realized_pnl: null  (throughout)
```
The order command returns success but NO position/P&L ever registers. ui-state
shows the replay-trading UI exists ("Reproducir trading", "Opciones de trading"),
so the panel is present but the trade does not surface a position. Paper-order
execution is NOT functional in this setup.

## 2. Order book depth — unavailable

```
data depth (OANDA:XAUUSD) -> {"success": false, "error": "DOM / Depth of Market panel not found."}
```
OANDA CFDs expose no L2/DOM; the order-flow directional edge is inaccessible.

## 3. Live streaming — works but non-additive

```
stream bars -> {"symbol":"OANDA:XAUUSD","resolution":"15","bar_time":1786391100,
                "open":4388.275,...,"volume":3776,"bar_index":300,"_stream":"bars"}
```
Emits JSONL on price change (poll default 500ms). Works, but does NOT address the
binding constraint: the 30-min hook's 300-bar pulls already capture every closed
bar (no gaps), and n_eff grows with WALL-CLOCK not poll frequency (h=4
non-overlapping = ~1 independent forecast/hour/instrument). stream would only cut
scoring latency (mature at close vs next tick) = marginal.
