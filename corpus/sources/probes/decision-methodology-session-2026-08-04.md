# Decision-methodology session receipt - 2026-08-04

Preserved facts from the trading analysis and decision-methodology session of 2026-08-04.
Collection was read-only; no order was placed and no broker was contacted.

## Runtime topology

- TradingView Desktop runs on **Windows**; the `tv` CLI and this Claude Code session run in **WSL2**.
- WSL2 mirrored networking makes the Windows-side CDP endpoint reachable from WSL at `127.0.0.1:9222`.
- Launcher on the Windows Desktop: `Abrir-TradingView-para-Claude.bat` relaunches TradingView with
  `--remote-debugging-port=9222`. The executable is `%LOCALAPPDATA%\tradingview-mcp\TradingView\TradingView.exe`.
  (Operator-confirmed Windows-side setup for this session; not reachable from WSL for direct file inspection.)
- CDP liveness was checked with `curl http://127.0.0.1:9222/json/version` and `/json/list`.

## Reading channel actually used this session

- The TradingView MCP server was **NOT loaded** into this Claude Code session: no `tv`/`tradingview_*`
  MCP tools were present in the session tool list. All chart reading was performed through the
  `tv` CLI (`node src/cli/index.js <cmd>`) plus reading the saved PNG under `screenshots/`.

## Live-feed bar cap (measured)

- The live feed returned at most **~300 bars per timeframe**, even though the OHLCV request path
  permits up to 500 (`src/core/data.js` `MAX_OHLCV_BARS = 500`). Preserved session pulls:
  - `gold_ohlcv_max.json` (XAUUSD 15m, live) = **300 bars**
  - `gold_daily.json` (XAUUSD daily, live) = **300 bars**, range 2025-06-05 .. 2026-08-03
  - `gold_ohlcv.json` (XAUUSD 15m, live) = 200 bars (count-limited request)

## Method scripts (scratchpad, ephemeral - not preserved in-corpus)

Analysis method was implemented in scratchpad scripts, referenced by these blocks as METHOD evidence:

- `gold_probabilistic.py` - linear-regression trend (slope + R^2), log-return volatility, zero-drift
  Monte Carlo cone (P5/P25/P50/P75/P95), drift-vs-zero-drift P(up).
- `gold_candles.py` - Wilder RSI(14) matching TradingView; empirical P(next bar up | pattern/RSI condition)
  with explicit sample-size caveat.
- `gold_backtest.py` - EMA(20/50) crossover daily backtest with transaction cost, expectancy per trade,
  win rate, max drawdown, Sharpe; explicit tiny-sample warning.
- `gold_grid.py` - EMA parameter grid on the same daily series, showing overfitting sensitivity and cost erosion.
- `replay_walk.py` - drives `tv replay step` bar-by-bar and applies a price-vs-EMA(9) rule, recording only
  hypothetical results (no money, no `replay trade`).
