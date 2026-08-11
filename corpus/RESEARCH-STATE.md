# TradingView MCP Capability Hardening - Research State

> DOCUMENT-cycle state. The fixed outline replaces gap discovery and is mirrored in Engram under `research/tradingview-mcp/*`.

<!-- research-state.v1 -->
schema: research-state.v1
covered_blocks: 25
gaps_closed: 25
known_gaps: 25
investigable_open: 0
requires_execution_open: 0
blocked_open: 0
deferred_open: 0
undocumented_findings: 0
<!-- /research-state.v1 -->

## Coverage

Two focuses share this corpus. Capability-hardening blocks use the `tradingview-` prefix and are
indexed in [INDEX.md](INDEX.md); the trading analysis and decision-methodology blocks use the
`tvdecision-` prefix and are indexed in [INDEX-DECISIONS.md](INDEX-DECISIONS.md).

- **Covered blocks**: 25 (capability-hardening B1..B3 + tvdecision B1..B22)
- **Coverage metric**: 25 / 25 outline items captured
- **Last iteration**: 2026-08-10 - calibration integrity: contamination guard, target-dedup, pooled cov50 illusion (tvdecision B21)
- **Last iteration**: 2026-08-11 - ACI adaptive conformal wired, walk-forward tested, REJECTED OOS (tvdecision B22)

## Document outline

| Priority | Outline item | Artifact type / source | Status |
|---|---|---|---|
| high | Capability hardening and Replay safety | JavaScript source and tests | captured - B1 |
| high | Offline verification and native review receipt | preserved local receipts | captured - B2 |
| high | OpenCode exposure, restart requirement, and broker isolation limit | local config and session receipt | captured - B3 |

## Document outline - tvdecision focus

Trading analysis and decision methodology (distinct topic; indexed in
[INDEX-DECISIONS.md](INDEX-DECISIONS.md)). Primary deliverable:
[DECISION-PLAYBOOK.md](DECISION-PLAYBOOK.md).

| Priority | Outline item | Artifact type / source | Status |
|---|---|---|---|
| high | Live-view setup and the fast chart-reading loop | JavaScript source + session receipt | captured - tvB1 |
| high | Honest probabilistic analysis (range, not point) | scratchpad method scripts + session receipt | captured - tvB2 |
| high | Rule validation: backtest + risk, and the Replay lesson | JavaScript source + scratchpad method scripts | captured - tvB3 |
| high | Persistent quant toolkit: upgraded numerical methods | `analysis/` Python source + live run | captured - tvB4 |
| high | Honest probability algorithms: fat-tail cones, conditional rigor, lookahead trap | `analysis/` Python source + live run | captured - tvB5 |
| high | Honest backtest engine: costs, out-of-sample, independent trades | `analysis/backtest.py` + tests + live run | captured - tvB6 |
| high | Regime and serial dependence: block bootstrap and the trend tautology | `analysis/` Python source + tests + live run | captured - tvB7 |
| high | Decision engine: gated BUY/SELL/NO-TRADE, flat by default | `analysis/decide.py` + tests + live run | captured - tvB8 |
| high | OHLCV collector: accumulating history past the 300-bar wall | `analysis/collect.py` + tests + live run | captured - tvB9 |
| high | Closing the feedback loop: gated recurring collection via hooks | `analysis/collect-hook.sh` + `.claude/settings.json` + live run | captured - tvB10 |
| high | Multi-market coverage: continuous-CFD expansion and the cash-index maturation boundary | `analysis/collect-hook.sh` + `analysis/forecast.py` + live run | captured - tvB11 |
| high | HAR-RV/Yang-Zhang cone volatility + conformal calibration layer | `analysis/quant.py` + `analysis/forecast.py` + `analysis/analyze.py` + TDD run | captured - tvB12 |
| high | Activating the conformal layer: shared cone recipe + backfill-seeded correction | `analysis/quant.py` + `analysis/backfill.py` + `analysis/collect-hook.sh` + backfill A/B | captured - tvB13 |
| high | Tier-2 refinements: CRPS, dedupe bugfix, gold hygiene, GJR rejected on A/B | `analysis/forecast.py` + `analysis/quant.py` + backfill A/B | captured - tvB14 |
| high | Which market forecasts best: per-market calibration ranking + recommendation | `analysis/forecast.py` + backfill per-market measurement | captured - tvB15 |
| high | Capability boundary: analysis works, execution/order-flow do not | `analysis/decide.py` + `src/cli/commands/replay.js` + `src/core/data.js` + replay demo | captured - tvB16 |
| high | Periodic monthly+weekly cadence with cone SL/TP + multi-TF annotation | `analysis/periodic.py` + `analysis/forecast.py` + `analysis/periodic-hook.sh` + live run | captured - tvB17 |
| high | Confluence: Fibonacci + accumulation + candles + panoramas | `analysis/quant.py` + `analysis/confluence.py` + live run | captured - tvB18 |
| high | Actionable layer: risk-based sizer + confluence price alerts | `analysis/forecast.py` + `src/cli/commands/alerts.js` + live run | captured - tvB19 |
| high | Walk-forward rigor: conformal 50%-band over-fits out-of-sample | `analysis/forecast.py` + backfill walk-forward | captured - tvB20 |
| high | Calibration integrity: contamination guard, target-dedup, pooled cov50 illusion | `analysis/forecast.py` + `analysis/test_forecast.py` + live measurement | captured - tvB21 |
| high | ACI adaptive conformal: wired, walk-forward tested, rejected out-of-sample | `analysis/forecast.py` + walk-forward | captured - tvB22 |

## Iteration history

| # | Date | Outline item | Block | Delegated? / model tier | New gaps uncovered |
|---|---|---|---|---|---|
| 1 | 2026-08-03 | Capability hardening and Replay safety | B1 | no / inline (targeted source reads) | 0 |
| 2 | 2026-08-03 | Offline verification and native review receipt | B2 | no / inline (preserved receipts) | 0 |
| 3 | 2026-08-03 | OpenCode exposure and isolation boundary | B3 | no / inline (targeted config reads) | 0 |
| 4 | 2026-08-04 | tvdecision: live-view setup and reading loop | tvB1 | no / inline (targeted source reads + session receipt) | 0 |
| 5 | 2026-08-04 | tvdecision: honest probabilistic analysis | tvB2 | no / inline (scratchpad method scripts) | 0 |
| 6 | 2026-08-04 | tvdecision: rule validation, backtest, Replay lesson | tvB3 | no / inline (source + method scripts) | 0 |
| 7 | 2026-08-05 | tvdecision: persistent quant toolkit, upgraded numerical methods | tvB4 | no / inline (authored `analysis/` source + live run) | 0 |
| 8 | 2026-08-05 | tvdecision: honest probability algorithms + lookahead fix | tvB5 | no / inline (authored `analysis/` source + tests + live run) | 0 |
| 9 | 2026-08-05 | tvdecision: honest backtest engine (costs/OOS/independent trades) | tvB6 | no / inline (authored `analysis/backtest.py` + tests + live run) | 0 |
| 10 | 2026-08-05 | tvdecision: regime detection + block bootstrap | tvB7 | no / inline (authored `analysis/` source + tests + live run) | 0 |
| 11 | 2026-08-05 | tvdecision: gated decision engine (BUY/SELL/NO-TRADE) | tvB8 | no / inline (authored `analysis/decide.py` + tests + live run) | 0 |
| 12 | 2026-08-05 | tvdecision: OHLCV collector (accumulate history to disk) | tvB9 | no / inline (authored `analysis/collect.py` + tests + live run) | 0 |
| 13 | 2026-08-05 | tvdecision: gated recurring collection via Claude Code hooks | tvB10 | no / inline (authored `analysis/collect-hook.sh` + settings wiring + live run) | 0 |
| 14 | 2026-08-10 | tvdecision: multi-market coverage + cash-index maturation boundary | tvB11 | no / inline (authored hook + forecast.py cites + live CDP run) | 0 |
| 15 | 2026-08-10 | tvdecision: HAR-RV/Yang-Zhang cone vol + conformal calibration layer | tvB12 | no / inline (TDD authored quant/forecast/analyze + live run) | 0 |
| 16 | 2026-08-10 | tvdecision: activating the conformal layer (shared recipe + backfill seed) | tvB13 | no / inline (TDD + 778-forecast backfill A/B) | 0 |
| 17 | 2026-08-10 | tvdecision: Tier-2 (CRPS, dedupe fix, gold hygiene, GJR rejected) | tvB14 | no / inline (TDD + 778-forecast GJR A/B) | 0 |
| 18 | 2026-08-10 | tvdecision: per-market calibration ranking + recommendation | tvB15 | no / inline (per-market backfill measurement) | 0 |
| 19 | 2026-08-10 | tvdecision: capability boundary (replay demo + execution/depth/stream probes) | tvB16 | no / inline (live replay demo + CDP probes) | 0 |
| 20 | 2026-08-10 | tvdecision: periodic monthly+weekly cadence + cone SL/TP + multi-TF annotation | tvB17 | no / inline (TDD + live cadence run) | 0 |
| 21 | 2026-08-10 | tvdecision: confluence (Fibonacci + accumulation + candles + panoramas) | tvB18 | no / inline (TDD + live confluence run) | 0 |
| 22 | 2026-08-10 | tvdecision: actionable layer (risk sizer + confluence alerts) | tvB19 | no / inline (TDD + live alerts/sizer) | 0 |
| 23 | 2026-08-10 | tvdecision: walk-forward rigor (conformal 50%-band over-fits OOS) | tvB20 | no / inline (TDD + backfill walk-forward) | 0 |
| 24 | 2026-08-10 | tvdecision: calibration integrity (contamination guard, target-dedup, pooled cov50 illusion) | tvB21 | no / inline (TDD + live measurement) | 1 (backlog #21: independent-subset cov50 CI) |
| 25 | 2026-08-11 | tvdecision: ACI adaptive conformal wired + rejected on walk-forward | tvB22 | no / inline (TDD + walk-forward OOS) | 0 |

## Blocked gaps

- none; document mode terminates on outline completion, not discovery exhaustion

## Stop control

- **Document outline remaining**: 0
- **Open gaps - read-only investigable**: 0 (not used by DOCUMENT mode)
- **Open gaps - requires-execution**: 0
- **Open gaps - blocked**: 0
- Budget cap: none

## Dismissed file types

The census was taken before scaffolding. DOCUMENT mode captures the supplied outline and does not audit the whole repository.

- `.js` - 1,976 files / 12.3 MB - dismissed: mostly installed dependencies; outline-relevant project JavaScript is cited directly in B1-B2.
- `.ts` - 1,203 files / 5.3 MB - dismissed: installed dependency declarations, outside the fixed capture outline.
- `.map` - 489 files / 4.0 MB - dismissed: generated dependency source maps, outside the fixed capture outline.
- `.json` - 280 files / 2.2 MB - dismissed: dependency metadata; the relevant review and OpenCode JSON records are cited in B2-B3.
- `.md` - 254 files / 1.5 MB - dismissed: dependency documentation; relevant project documentation is cited in B1-B3.
- `(no ext)` - 213 files / 0.3 MB - dismissed: dependency executables/metadata, outside the fixed capture outline.
- `.cjs` - 122 files / 1.4 MB - dismissed: installed dependency runtime files, outside the fixed capture outline.
- `.cts` - 121 files / 0.4 MB - dismissed: installed dependency declarations, outside the fixed capture outline.
- `.jst` - 50 files / 0.1 MB - dismissed: dependency templates, outside the fixed capture outline.
- `.yml` - 46 files / 0.0 MB - dismissed: dependency/CI metadata, outside the fixed capture outline.
- `.mjs` - 29 files / 0.6 MB - dismissed: installed dependency modules, outside the fixed capture outline.
- `.mts` - 16 files / 0.1 MB - dismissed: installed dependency declarations, outside the fixed capture outline.
- `.def` - 10 files / 0.0 MB - dismissed: dependency native-build metadata, outside the fixed capture outline.
- `.db-wal` - 1 file / 4.0 MB - dismissed: local tool cache, not subject evidence.
- `.db` - 1 file / 1.8 MB - dismissed: local tool cache, not subject evidence.
