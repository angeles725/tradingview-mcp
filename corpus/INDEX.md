# TradingView MCP Capability Hardening - Master Index

**Updated**: 2026-08-03
**Analyzed system**: upstream `tradesdontlie/tradingview-mcp` at commit `c05b8f5755ed8e64ea242de88ddbf46aa24d56a4`, plus the approved uncommitted capability-hardening candidate.
**Method**: Research-SDD DOCUMENT cycle using direct source reading, offline Node.js tests, local configuration inspection, and a preserved native-review receipt. No TradingView/CDP or financial operation was performed.

This index covers three cited blocks. The generated flat catalog is [CATALOG.md](CATALOG.md).

## Marker legend

`[CERT]` local primary source; `[CERT-hw]` preserved output from the local controlled session; `[INFER]` explicit deduction.

## Layer summary

| Layer | Topic area | Blocks | Status | One-line summary |
|---|---|---|---|---|
| 1 | Capability boundaries | 1 | complete | Exact acknowledgments fail closed before dangerous execution paths. |
| 2 | Verification authority | 2 | complete | Offline suites and native four-lens review approved the frozen candidate. |
| 3 | Runtime exposure | 3 | complete | OpenCode exposes Replay navigation only; restart and broker-isolation boundaries remain. |

## Full map

| # | Block | File | Key topics |
|---|---|---|---|
| 1 | Fail-closed capability boundaries | [tradingview-block1.md](tradingview-block1.md) | upstream identity, exact env acknowledgments, core/CLI/MCP ordering, independent Replay navigation |
| 2 | Offline verification and native review | [tradingview-block2.md](tradingview-block2.md) | 121 focused tests, 128 safe tests, lint, four review lenses, approved target identity |
| 3 | Minimal OpenCode exposure and residual boundary | [tradingview-block3.md](tradingview-block3.md) | enabled Replay tools, denied mutation surfaces, restart requirement, broker/demo isolation limit |

## Document outline

- [x] Capability hardening and Replay safety -> [Block 1]
- [x] Offline evidence and native review receipt -> [Block 2]
- [x] Minimal OpenCode exposure, restart requirement, and broker isolation limit -> [Block 3]

## Coverage

- **Document outline**: 3 / 3 items captured
- **Discovery backlog**: not applicable (`method: document-cycle-external`)
