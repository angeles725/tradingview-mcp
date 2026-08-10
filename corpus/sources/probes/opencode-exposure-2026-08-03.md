# OpenCode exposure receipt

Date: 2026-08-03
Configuration inspected read-only: `/home/cristian/.config/opencode/opencode.json`

## Configured Replay exposure for `gentle-orchestrator`

- Enabled: `tradingview_replay_start`
- Enabled: `tradingview_replay_step`
- Enabled: `tradingview_replay_autoplay`
- Enabled: `tradingview_replay_status`
- Enabled: `tradingview_replay_stop`
- Not enabled: `tradingview_replay_trade`

The agent-specific allowlist does not enable generic UI mutation (`ui_click`, keyboard, type, mouse), `ui_evaluate`, or broker-order tools. It does enable the read-only locator `tradingview_ui_find_element`; that is not a mutation tool.

## Runtime observation

The current OpenCode session started before the allowlist change and exposes no `tradingview_*` function namespace to this agent. The running process therefore still requires a restart before the newly configured Replay navigation tools become available. This receipt records the session/tool-registration observation; no TradingView tool was invoked.

## Global default

The global `tools` map keeps `tradingview_*` false. Exposure is an explicit per-agent exception, not a global enablement.
