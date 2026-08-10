# TradingView MCP Capability Hardening Runbook

This runbook is the operational summary of the cited Research-SDD blocks. Start with the boundary, not the feature list: Replay navigation is available by design, while simulated position changes and arbitrary page JavaScript are separate default-denied capabilities.

## Quick path

1. Confirm the checkout is upstream `tradesdontlie/tradingview-mcp` at the intended revision. See [Block 1](tradingview-block1.md#11---upstream-identity-cert-hw).
2. Keep both dangerous capability environment variables unset for routine use.
3. Restart OpenCode after changing its tool allowlist; configuration changes do not retrofit the already-running session.
4. Verify the active agent exposes Replay `start`, `step`, `autoplay`, `status`, and `stop`, but not `replay_trade`.
5. Disconnect every real broker independently before any Replay practice. The MCP cannot prove account or broker isolation.

## Capability matrix

| Surface | Routine state | Reason |
|---|---|---|
| `ui_evaluate` | unavailable and fail-closed | Arbitrary JavaScript requires its exact startup acknowledgment. |
| `replay_trade` | unavailable and fail-closed | Simulated position mutation requires a separate exact startup acknowledgment. |
| Replay navigation | agent allowlisted after restart | Navigation is structurally independent from simulated trade mutation. |
| Generic UI mutation | unavailable to the orchestrator | Prevents prompts from clicking or typing around order-entry surfaces. |
| Broker operations | unavailable | This MCP has no broker-order integration or broker-isolation oracle. |

## Offline verification

Run only the bounded set when TradingView/CDP must remain untouched:

```bash
git diff --check
node --test tests/capabilities.test.js tests/sanitization.test.js tests/replay.test.js
npm run test:safe
npm run lint
```

Expected receipt: 121 focused tests, 128 safe-suite tests, and ESLint with zero errors plus four known warnings. See [Block 2](tradingview-block2.md).

## Non-negotiable boundary

Replay mode is not evidence of paper/demo isolation. Before practice, verify broker disconnection through a channel outside this MCP. If that cannot be established, do not perform simulated trade actions or generic UI automation near order-entry controls.

## Evidence map

- [Block 1](tradingview-block1.md): implementation and registration boundaries.
- [Block 2](tradingview-block2.md): offline receipts and native review approval.
- [Block 3](tradingview-block3.md): OpenCode exposure, restart requirement, and residual isolation limit.
