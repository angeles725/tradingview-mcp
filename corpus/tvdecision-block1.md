# Block 1 - Live-view setup and the fast chart-reading loop

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how the live chart is brought up over WSL2 -> Windows CDP, the exact read-only reading channel
> used this session, and the fixed six-command reading loop with its size caveats.
>
> Subject version: upstream commit `c05b8f5755ed8e64ea242de88ddbf46aa24d56a4`; session 2026-08-04.
>
> Sources: `../src/cli/index.js`, `../src/cli/commands/health.js`, `../src/cli/commands/chart.js`,
> `../src/cli/commands/data.js`, `../src/cli/commands/capture.js`, `../src/cli/commands/replay.js`,
> `../src/core/data.js`, `sources/probes/decision-methodology-session-2026-08-04.md`.
> Method: targeted local source reading plus preserved session facts. `[CERT]` means local primary
> source (`file:line`); `[CERT-hw]` means a preserved fact from the controlled session of 2026-08-04;
> `[INFER]` is an explicit deduction.
>
> Setup and reading-loop layer. Connects [Block 2] (probabilistic analysis) and [Block 3] (rule validation).

---

## 1.1 - WSL2 to Windows CDP topology `[CERT-hw]`

TradingView Desktop runs on Windows while the `tv` CLI and the Claude Code session run in WSL2; WSL2
mirrored networking makes the Windows CDP endpoint reachable from WSL at `127.0.0.1:9222`
(`sources/probes/decision-methodology-session-2026-08-04.md`). The Windows-side launcher
`Abrir-TradingView-para-Claude.bat` relaunches TradingView with `--remote-debugging-port=9222`, and the
executable lives at `%LOCALAPPDATA%\tradingview-mcp\TradingView\TradingView.exe`. Liveness is confirmed
out of band with `curl http://127.0.0.1:9222/json/version` and `curl http://127.0.0.1:9222/json/list`
before any reading.

## 1.2 - Reading channel: CLI + PNG, MCP not loaded `[CERT-hw]`

The TradingView MCP server was NOT loaded into this Claude Code session; no `tv`/`tradingview_*` MCP
tools were present. All chart reading went through the `tv` CLI, invoked as
`node src/cli/index.js <cmd>`, plus reading the saved screenshot PNG under `screenshots/`
(`sources/probes/decision-methodology-session-2026-08-04.md`). The CLI is the same tool surface as the
MCP: every tool is reachable as a CLI command (`../src/cli/index.js:9`), so the absence of the MCP
does not reduce what can be read - it only changes the invocation path.

## 1.3 - The fast reading loop, six commands `[CERT]`

The reading loop runs in a fixed order, each step a single CLI command:

| Step | Command | Returns | Source |
|---|---|---|---|
| 1 | `node src/cli/index.js state` | symbol, timeframe, chart type, indicator entity IDs | `../src/cli/commands/chart.js:5` |
| 2 | `node src/cli/index.js quote` | real-time price / OHLC / volume snapshot | `../src/cli/commands/data.js:4` |
| 3 | `node src/cli/index.js values` | current numeric values from visible indicators | `../src/cli/commands/data.js:21` |
| 4 | `node src/cli/index.js data lines` / `labels` / `tables` | Pine-drawn levels, annotations, tables | `../src/cli/commands/data.js:29`, `../src/cli/commands/data.js:37`, `../src/cli/commands/data.js:46` |
| 5 | `node src/cli/index.js ohlcv --summary` | compact price-action stats (no per-bar dump) | `../src/cli/commands/data.js:9` |
| 6 | `node src/cli/index.js screenshot` | saved PNG path for visual confirmation | `../src/cli/commands/capture.js:4` |

Step 1 supplies the entity IDs the later steps reference; calling it once at the start avoids
re-scanning. Pine-drawn graphics (`line.new`, `label.new`, `table.new`, `box.new`) are invisible to
`values` and require the `data` subcommands (`../src/cli/commands/data.js:26`).

## 1.4 - Size caveats: request 500, live feed 300 `[CERT]`

The OHLCV request path caps at 500 bars (`../src/core/data.js:7`) and clamps the requested count to
that ceiling (`../src/core/data.js:138`). Independently of that code limit, the live feed returned at
most ~300 bars per timeframe this session `[CERT-hw]` (`gold_ohlcv_max.json` = 300 bars,
`gold_daily.json` = 300 bars; `sources/probes/decision-methodology-session-2026-08-04.md`). The
practical read caveats: prefer `ohlcv --summary` over dumping bars, use `data` `--filter` to target one
study, and treat ~300 bars as the honest history horizon per timeframe rather than assuming deeper
history is available `[INFER]`.

## 1.5 - Connections

- **[Block 2]** - consumes the bars read here to produce a probabilistic range, not a point forecast.
- **[Block 3]** - uses `replay` (read here at `../src/cli/commands/replay.js:8`) for risk-free rule practice.
- **[Block 1 of the capability-hardening focus]** (`tradingview-block1.md`) - documents that Replay
  navigation is available while dangerous mutation surfaces are default-denied.
