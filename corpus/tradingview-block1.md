# Block 1 - Fail-closed capability boundaries

> Research of **TradingView MCP capability hardening**: repository identity, exact startup acknowledgments, gate ordering, and Replay navigation independence. It does not claim broker isolation.
>
> Subject version: upstream commit `c05b8f5755ed8e64ea242de88ddbf46aa24d56a4` plus candidate `sha256:557daf52c79eafc735ea3f79b1458f907399ea87e35b2404177891d309c6c69e`.
>
> Sources: `../src/capabilities.js`, `../src/core/ui.js`, `../src/core/replay.js`, `../src/tools/replay.js`, `../src/cli/commands/replay.js`, `../tests/capabilities.test.js`, `../tests/replay.test.js`, `sources/probes/repository-identity-2026-08-03.md`.
> Method: targeted local source reading plus offline boundary tests. `[CERT]` means local primary source; `[CERT-hw]` means preserved output from the controlled local session; `[INFER]` is an explicit deduction.
>
> Security boundary layer. Connects [Block 2] (verification authority) and [Block 3] (runtime exposure and residual limits).

---

## 1.1 - Upstream identity `[CERT-hw]`

The subject is the upstream `tradesdontlie/tradingview-mcp` repository at `c05b8f5`, not the Jackson fork. The preserved Git receipt records both the full HEAD and origin URL (`sources/probes/repository-identity-2026-08-03.md:3`, `sources/probes/repository-identity-2026-08-03.md:4`).

## 1.2 - Exact, independent acknowledgments `[CERT]`

Arbitrary page JavaScript and simulated Replay trades use separate environment variables and separate exact acknowledgment values (`../src/capabilities.js:1`, `../src/capabilities.js:2`, `../src/capabilities.js:3`, `../src/capabilities.js:4`). Both guards compare with strict inequality and throw unless the exact value is present (`../src/capabilities.js:7`, `../src/capabilities.js:15`). Generic truthy or near-match values therefore fail closed, as tested for JavaScript (`../tests/capabilities.test.js:41`) and Replay (`../tests/replay.test.js:336`).

## 1.3 - Gate before dangerous work and validation `[CERT]`

`uiEvaluate` calls `requireArbitraryPageJs` before expression validation and before selecting or invoking `evaluate` (`../src/core/ui.js:300`, `../src/core/ui.js:301`, `../src/core/ui.js:302`, `../src/core/ui.js:305`). Its offline test proves the injected evaluator remains untouched while disabled (`../tests/capabilities.test.js:27`, `../tests/capabilities.test.js:38`).

`trade` calls `requireReplayTrading` before action validation, dependency resolution, Replay API lookup, or CDP evaluation (`../src/core/replay.js:107`, `../src/core/replay.js:108`, `../src/core/replay.js:109`, `../src/core/replay.js:112`). The core test measures zero Replay-API and evaluator calls while disabled (`../tests/replay.test.js:316`, `../tests/replay.test.js:332`, `../tests/replay.test.js:333`).

The actual CLI `trade` handler delegates directly to gated core logic without pre-validating a missing action (`../src/cli/commands/replay.js:4`, `../src/cli/commands/replay.js:5`, `../src/cli/commands/replay.js:37`). The MCP registration deliberately accepts an optional unknown envelope so SDK schema validation cannot preempt the capability denial; strict action validation remains in core after opt-in (`../src/tools/replay.js:31`, `../src/tools/replay.js:32`, `../src/tools/replay.js:34`). The in-memory SDK test sends valid, arbitrary-shaped, and missing actions and receives capability denial rather than action validation (`../tests/replay.test.js:411`, `../tests/replay.test.js:412`, `../tests/replay.test.js:421`, `../tests/replay.test.js:422`).

## 1.4 - Replay navigation remains independent `[CERT]`

The trade gate appears only in `trade`; `start`, `step`, `autoplay`, `stop`, and `status` resolve their own Replay dependencies without calling `requireReplayTrading` (`../src/core/replay.js:20`, `../src/core/replay.js:60`, `../src/core/replay.js:78`, `../src/core/replay.js:96`, `../src/core/replay.js:126`). The status test explicitly runs with an empty environment and succeeds (`../tests/replay.test.js:440`, `../tests/replay.test.js:463`, `../tests/replay.test.js:464`).

## 1.5 - Connections

- **[Block 2]** - records the offline verification counts and native review authority for these boundaries.
- **[Block 3]** - maps the independent Replay surface to the minimal OpenCode allowlist and documents what the MCP cannot prove.
