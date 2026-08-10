# Block 3 - Minimal OpenCode exposure and residual isolation boundary

> Research of **the running OpenCode integration boundary**: per-agent Replay allowlist, restart requirement, and the broker/demo isolation claim that remains unprovable. It does not interact with TradingView or CDP.
>
> Subject version: OpenCode configuration inspected 2026-08-03; TradingView MCP candidate `sha256:557daf52c79eafc735ea3f79b1458f907399ea87e35b2404177891d309c6c69e`.
>
> Sources: `/home/cristian/.config/opencode/opencode.json`, `../SECURITY.md`, `../README.md`, `sources/probes/opencode-exposure-2026-08-03.md`.
> Method: read-only local configuration inspection plus current-session tool-registry observation. `[CERT]` means local primary source; `[CERT-hw]` means preserved output from the controlled local session; `[INFER]` is an explicit deduction.
>
> Operational boundary layer. Connects [Block 1] (independent Replay navigation) and [Block 2] (approved evidence).

---

## 3.1 - Replay-only mutation exposure `[CERT]`

Within the Replay surface, `gentle-orchestrator` enables only `replay_start`, `replay_step`, `replay_autoplay`, `replay_status`, and `replay_stop` (`/home/cristian/.config/opencode/opencode.json:61`, `/home/cristian/.config/opencode/opencode.json:62`, `/home/cristian/.config/opencode/opencode.json:63`, `/home/cristian/.config/opencode/opencode.json:64`, `/home/cristian/.config/opencode/opencode.json:65`). `replay_trade` is absent from that allowlist. The global default remains `tradingview_*: false` (`/home/cristian/.config/opencode/opencode.json:451`, `/home/cristian/.config/opencode/opencode.json:452`).

The allowlist does not enable generic UI mutation, arbitrary JavaScript, or broker-order tools. It does separately enable `ui_find_element`, a read-only locator, which must not be confused with UI mutation (`/home/cristian/.config/opencode/opencode.json:67`). The complete exposure interpretation is preserved in `sources/probes/opencode-exposure-2026-08-03.md:5` through `sources/probes/opencode-exposure-2026-08-03.md:14`.

## 3.2 - Restart still required `[CERT-hw]`

The current OpenCode process began before the allowlist change and exposes no `tradingview_*` function namespace to this agent. The preserved session receipt records that the configured Replay navigation tools therefore require an OpenCode restart before they become available (`sources/probes/opencode-exposure-2026-08-03.md:16`, `sources/probes/opencode-exposure-2026-08-03.md:18`). No TradingView tool was invoked to establish this fact.

## 3.3 - Broker and account isolation remain unprovable `[CERT]`

The MCP can describe Replay state, but it cannot inspect or prove broker disconnection, account type, or demo/paper identity. The project security policy states that the gate does not inspect account type or broker connectivity and instructs users to keep real brokers disconnected (`../SECURITY.md:49`, `../SECURITY.md:51`). The README likewise warns that Replay and paper trading are not equivalent to enforced isolation (`../README.md:81`).

Therefore the safe operating rule is external to this MCP: use Replay navigation only after independently disconnecting real brokers. `[INFER]` A future live session showing Replay mode would still not certify broker isolation, because the missing observation channel is broker/account identity, not Replay state.

## 3.4 - Connections

- **[Block 1]** - explains why navigation can remain available while simulated trade mutation stays gated.
- **[Block 2]** - provides the offline and adversarial evidence supporting this restricted exposure.
