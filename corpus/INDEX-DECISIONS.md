# TradingView Trading Analysis & Decision Methodology - Focus Index

**Updated**: 2026-08-05
**Focus**: `tvdecision` (distinct from the capability-hardening focus in [INDEX.md](INDEX.md)).
**Analyzed system**: upstream `tradesdontlie/tradingview-mcp` at commit
`c05b8f5755ed8e64ea242de88ddbf46aa24d56a4`, read live via the `tv` CLI over WSL2 -> Windows CDP.
**Method**: Research-SDD DOCUMENT cycle. Read-only local source reading plus preserved session facts and
scratchpad method scripts. No order was placed and no broker was contacted.

This index covers three cited blocks and one actionable deliverable. The shared flat catalog is
[CATALOG.md](CATALOG.md); the shared machine state is [RESEARCH-STATE.md](RESEARCH-STATE.md).

## Marker legend

`[CERT]` local primary source (`file:line`); `[CERT-hw]` preserved test/measurement from a controlled
session; `[CERT-live]` preserved live-feed measurement (2026-08-05 XAUUSD 15m run); `[INFER]` explicit
deduction.

## Primary deliverable

- **[DECISION-PLAYBOOK.md](DECISION-PLAYBOOK.md)** - copy-paste, command-forward checklist: is-it-live ->
  read in 6 commands -> assess (don't predict) -> guardrails -> Replay practice. This is the speed lever.

## Block map

| # | Block | File | Key topics |
|---|---|---|---|
| 1 | Live-view setup and the fast reading loop | [tvdecision-block1.md](tvdecision-block1.md) | WSL2->Windows CDP, MCP-not-loaded / CLI+PNG channel, six-command loop, 500-request vs 300-live bar cap |
| 2 | Honest probabilistic analysis: range, not point | [tvdecision-block2.md](tvdecision-block2.md) | regression trend + R^2, log-return volatility, zero-drift Monte Carlo cone, empirical P(up) + sample-size caveat, direction guardrail |
| 3 | Rule validation: backtest, risk, and the Replay lesson | [tvdecision-block3.md](tvdecision-block3.md) | next-bar backtest + expectancy, the three traps (sample/overfit/costs), Replay practice, real-money readiness, broker-isolation limit |
| 4 | Persistent quant toolkit: upgraded numerical methods | [tvdecision-block4.md](tvdecision-block4.md) | ephemeral->tested `analysis/`, OLS+CI+Theil-Sen trend, volatility family (close-to-close/EWMA/Parkinson/Garman-Klass/GARCH(1,1)), clustering-aware cone sigma |
| 5 | Honest probability algorithms: fat-tail cones, conditional rigor, lookahead trap | [tvdecision-block5.md](tvdecision-block5.md) | 3-model Monte Carlo (gaussian/bootstrap/student-t), Wilson CI + binomial test, the lookahead-leakage fix + regression guard |
| 6 | Honest backtest engine: costs, out-of-sample, independent trades | [tvdecision-block6.md](tvdecision-block6.md) | next-open fills (no lookahead), cost subtraction, bootstrap CI + thin-sample, in/out-of-sample split, the overlapping-trades autocorrelation fix, random-walk falsifiability |
| 7 | Regime and serial dependence: block bootstrap and the trend tautology | [tvdecision-block7.md](tvdecision-block7.md) | Politis-Romano stationary block bootstrap, Lo-MacKinlay variance ratio, rolling-R^2 regime labels, per-regime expectancy split, VR normalization fix |
| 8 | Decision engine: gated BUY/SELL/NO-TRADE, flat by default | [tvdecision-block8.md](tvdecision-block8.md) | three veto gates (direction/edge/risk-reward), fixed-risk sizing, safety-by-omission (no order path), walk-forward process feedback |
| 9 | OHLCV collector: accumulating history past the 300-bar wall | [tvdecision-block9.md](tvdecision-block9.md) | dedup-by-time CSV store, forming-bar update, atomic save, stdlib-only, re-emit as bars JSON to feed the analysis tools |
| 10 | Closing the feedback loop: gated recurring collection via hooks | [tvdecision-block10.md](tvdecision-block10.md) | hooks-not-cron rationale, throttle + TV-reachable gates, detached pull (~20ms), SessionStart+Stop wiring, portable path resolution |
| 11 | Multi-market coverage: continuous-CFD expansion and the cash-index maturation boundary | [tvdecision-block11.md](tvdecision-block11.md) | five markets (CN/EU/US/JP/KR), continuous-vs-session boundary, horizon-in-bars trap, KOSPI orphan record, hook set 6->10, dual-gold-key hygiene note |
| 12 | HAR-RV/Yang-Zhang cone volatility + conformal calibration layer | [tvdecision-block12.md](tvdecision-block12.md) | Rogers-Satchell/Yang-Zhang gap-robust vol, causal HAR-RV forecast, GARCH+HAR blended cone sigma, split-conformal/CQR correction + ACI, closed hook loop, layer dormant until min_n |
| 13 | Activating the conformal layer: shared cone recipe + backfill-seeded correction | [tvdecision-block13.md](tvdecision-block13.md) | 778-forecast backfill A/B (new blend ~= old, cov90 nominal, 50% over-dispersed), drift bug in backfill._cones, quant.cone_sigma single source of truth, --extra-log pooling, hook seeds conformal.json from backfill, live gold verification |
| 14 | Tier-2 refinements: CRPS, dedupe bugfix, gold hygiene, GJR rejected on A/B | [tvdecision-block14.md](tvdecision-block14.md) | CRPS full-distribution score, _dedupe prefers scored (latent bug), unify dual gold key, GJR-GARCH investigated + rejected (778-window A/B: null gain, 3-4x cost) |
| 15 | Which market forecasts best: per-market calibration ranking + recommendation | [tvdecision-block15.md](tvdecision-block15.md) | SPX500USD best-calibrated (calErr 0.06), EURUSD/GBPUSD sharpest, gold/DAX under-cover 90% (understate risk), Nasdaq/Nikkei over-disperse 50%; FX low pinball = low vol not skill |

## Companion deliverable

- **[../analysis/README.md](../analysis/README.md)** - the persistent toolkit added this session: `quant.py`
  (numerical primitives), `analyze.py` (stdin runner), and tests. Run: `node src/cli/index.js ohlcv
  --count 300 | <venv>/python analysis/analyze.py --tf 15 --horizon 16`.

## Document outline

- [x] Live-view setup and the fast chart-reading loop -> [Block 1]
- [x] Honest probabilistic analysis (range, not point) -> [Block 2]
- [x] Rule validation: backtest + risk, and the Replay lesson -> [Block 3]
- [x] Persistent quant toolkit: upgraded numerical methods -> [Block 4]
- [x] Honest probability algorithms: fat-tail cones, conditional rigor, lookahead trap -> [Block 5]
- [x] Honest backtest engine: costs, out-of-sample, independent trades -> [Block 6]
- [x] Regime and serial dependence: block bootstrap and the trend tautology -> [Block 7]
- [x] Decision engine: gated BUY/SELL/NO-TRADE, flat by default -> [Block 8]
- [x] OHLCV collector: accumulating history past the 300-bar wall -> [Block 9]
- [x] Closing the feedback loop: gated recurring collection via hooks -> [Block 10]
- [x] Multi-market coverage: continuous-CFD expansion and the cash-index maturation boundary -> [Block 11]
- [x] HAR-RV/Yang-Zhang cone volatility + conformal calibration layer -> [Block 12]
- [x] Activating the conformal layer: shared cone recipe + backfill-seeded correction -> [Block 13]
- [x] Tier-2 refinements: CRPS, dedupe bugfix, gold hygiene, GJR rejected on A/B -> [Block 14]
- [x] Which market forecasts best: per-market calibration ranking + recommendation -> [Block 15]

## Coverage

- **Document outline (tvdecision focus)**: 15 / 15 items captured
- **Discovery backlog**: not applicable (`method: document-cycle`)
