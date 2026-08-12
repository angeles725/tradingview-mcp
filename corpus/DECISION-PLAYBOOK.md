# TradingView Decision Playbook

Copy-paste checklist to make chart-analysis decisions faster and better. Execute top to bottom.
All commands run from `/home/cristian/TRADINGVIEW` in WSL2; TradingView Desktop runs on Windows.
Backing evidence: [tvdecision-block1](tvdecision-block1.md), [block2](tvdecision-block2.md),
[block3](tvdecision-block3.md).

## 1. Is it live?

```bash
# On the Windows Desktop, double-click the launcher (relaunches TV with CDP on 9222):
#   Abrir-TradingView-para-Claude.bat
#   -> exe: %LOCALAPPDATA%\tradingview-mcp\TradingView\TradingView.exe --remote-debugging-port=9222

# From WSL2 (mirrored networking reaches the Windows CDP endpoint):
curl -s http://127.0.0.1:9222/json/version   # expect a JSON version blob
curl -s http://127.0.0.1:9222/json/list      # expect the open TradingView target(s)
node src/cli/index.js status                 # CDP health via the CLI
```

If `curl` fails: relaunch via the `.bat` on Windows. The MCP is NOT loaded in this session - read via the
`tv` CLI + the saved PNG, never via MCP tools.

## 2. Read the chart in 6 commands

```bash
node src/cli/index.js state                  # symbol, timeframe, chart type, indicator entity IDs (run ONCE first)
node src/cli/index.js quote                  # real-time price / OHLC / volume snapshot
node src/cli/index.js values                 # numeric values from visible indicators (RSI, MACD, EMAs...)
node src/cli/index.js data lines             # Pine-drawn horizontal levels  (add --filter <name> to target one study)
node src/cli/index.js data labels            # Pine-drawn text annotations   (also: data tables / data boxes)
node src/cli/index.js ohlcv --summary        # compact price-action stats (NOT a full bar dump)
node src/cli/index.js screenshot             # saved PNG path for visual confirmation
```

Size caveats: OHLCV request caps at 500 bars, but the **live feed returns ~300 bars/timeframe** - treat
that as the real history horizon. Prefer `--summary`; use `--filter` to avoid scanning every study; a
screenshot is cheaper context than dumping bars.

## 3. Assess, don't predict

- **Trend** - linear regression on closes: report slope (price/bar) AND R^2; R^2 < ~0.3 = noise, ignore the slope.
- **Momentum** - RSI(14, Wilder, matches TradingView); high/"overbought" RSI does NOT mean sell in a strong trend.
- **Volatility** - stdev of log returns, scaled to a daily %; sizes the move, says nothing about direction.
- **Probabilistic range** - zero-drift Monte Carlo cone, report P5..P95 over the horizon; deliver the BAND, not the median.

**Automated (preferred):** the persistent toolkit runs all of the above at once, with upgrades - see
[../analysis/README.md](../analysis/README.md) and [Block 4](tvdecision-block4.md) / [Block 5](tvdecision-block5.md):

```bash
VENV=~/.local/share/research-sdd-tools/venv/bin/python3
node src/cli/index.js ohlcv --count 300 | $VENV analysis/analyze.py --symbol XAUUSD --tf 15 --horizon 16
```

It reports OLS+CI+Theil-Sen trend, five volatility estimators (incl. EWMA/GARCH), a three-model Monte
Carlo cone (gaussian/bootstrap/Student-t, so fat tails are visible), and conditional P(next up) with Wilson
CIs + a binomial test. A lookahead-leakage guard (`analysis/test_analyze.py`) blocks fake 100% edges.

**Directional state (descriptive, NOT predictive)** - [Block 25](tvdecision-block25.md) /
[Block 26](tvdecision-block26.md): `bash analysis/direction.sh OANDA:XAUUSD` reads a multi-timeframe
up/down/flat state with explicit confidence across 1m..1M. Read it as CONTEXT (trend/regime), never as a
forecast: a pooled significance test proved directional skill is ZERO or NEGATIVE at every timeframe
(no TF beats the base-rate best-constant predictor), and an orthogonal COT positioning probe found no edge
either. The tool stamps each call with its real historical hit-rate for exactly this reason.

**Cone coverage caveat** - [Block 28](tvdecision-block28.md): before sizing a stop off a cone band, check
the per-instrument coverage flag (`analysis/cone_coverage.py`, `corpus/cone-coverage.json`). Some symbol|tf
cones run too tight - notably gold/silver at D/W, whose nominal 90% band historically held only ~79-85%.
`analyze.py` prints the warning inline; widen the stop where the flag says the band lies. This stays a
diagnostic FLAG on purpose: every attempt to auto-widen it (conformal 50%-band, ACI, block-bootstrap,
vol-floor, and the single-scalar widener in [Block 30](tvdecision-block30.md)) over-fit out-of-sample.

## 4. Decision guardrails (non-negotiable)

- Deliver a **range with a probability**, never a single point price.
- **Direction is not forecastable here** - proven, not assumed: zero/negative skill at every timeframe
  ([Block 26](tvdecision-block26.md)), and orthogonal data (COT) adds none ([Block 27](tvdecision-block27.md)).
  Trend/RSI/GARCH refine size and confidence, never the arrow.
- **Validate any rule by an honest backtest** (costs + enough trades) BEFORE risking real money.
- **Risk management first**: position sizing and stop-loss decide survival, not a better predictor.
- **The tool cannot prove broker/demo isolation** - confirm the live broker is disconnected out of band before any practice.

## 5. Practice safely (Replay)

```bash
node src/cli/index.js replay start --date 2025-03-01   # enter Bar Replay at a date
node src/cli/index.js replay step                      # advance one bar
node src/cli/index.js replay autoplay --speed 500      # auto-advance (ms per bar; lower = faster)
node src/cli/index.js replay status                    # position / current date
node src/cli/index.js replay stop                      # return to realtime
```

`replay trade` (simulated position change) is default-denied and out of scope for read-only practice.
Trend-following loses small in chop and wins big in trends - practice reveals its shape; a static
indicator reading hides it.
