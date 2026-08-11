# Block 21 - Calibration integrity: contamination guard, target-based dedup, and the pooled cov50 illusion

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> a session that hardened the CALIBRATION RECORD itself — the log the coverage numbers are read from.
> It fixes a cross-symbol contamination bug, replaces exact-made_at dedup with target-based dedup, and
> shows the "live 50% band runs wide" alarm is a pooled-overlapping-sample illusion, not a model defect.
>
> Subject version: `analysis/forecast.py` on branch `feat/quant-analysis-toolkit`. Session 2026-08-10.
>
> Sources: `analysis/forecast.py` + `analysis/test_forecast.py` (local primary source). Preserved run:
> `sources/probes/calibration-integrity-session-2026-08-10.md`.
> Method: read-only citation of authored code + a preserved in-session measurement + TDD. `[CERT]` marks a
> local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block. Rigor layer — audits the calibration LOG feeding [Block 15] / [Block 20].

---

## 21.1 - The cross-symbol contamination bug `[CERT]`

`score_pending` matures a pending forecast with `nearest_close(src, target_unix, tol)`, which matches on
TIME ONLY (`analysis/forecast.py`). Its own docstring warned that a multi-symbol live window can therefore
score one symbol against another's bars at the same instant. It happened: two GBPUSD records carried
`realized.close ≈ 159` (USDJPY's price; GBPUSD trades ≈ 1.35), a +11681% "move"
(`sources/probes/calibration-integrity-session-2026-08-10.md`) `[CERT-live]`. It inflated the pooled
gaussian cov90 count and dropped GBPUSD's cov90 to a spurious 0.625.

## 21.2 - The guard: MAX_REALIZED_JUMP `[CERT]`

`MAX_REALIZED_JUMP = 0.20`. After `nearest_close` returns `rc`, `score_pending` skips scoring when
`S0 and abs(rc/S0 - 1) > MAX_REALIZED_JUMP`, leaving the record pending for a symbol-correct source
(`analysis/forecast.py`) `[CERT]`. Defense-in-depth BEYOND the existing `--symbol` filter: a move that large
over these horizons is impossible, so it is refused rather than trusted. Test
`test_score_pending_rejects_absurd_cross_symbol_jump`. The 2 corrupt rows were reset to pending; re-resolve
via `score --store` found no store bar at their target → honestly unresolved, not fabricated `[CERT-live]`.

## 21.3 - Target-based dedup replaces exact-made_at dedup `[CERT]`

`_dedupe`'s key changed from `(symbol, tf, made_at_unix, horizon)` to `(symbol, tf, horizon, target_unix)`
(`analysis/forecast.py`) `[CERT]`. `[INFER]` Two forecasts share a `target_unix` only if built from the same
last bar, so they are genuinely redundant; keying on made_at let overlapping hook ticks record the same target
hour twice and double-count it. Merge rule preserved: a SCORED copy beats an unscored one (never lose a
maturation), then the freshest `made_at` wins. `_dedupe` is now also applied inside the `score` command before
`write_log`, so the persisted log self-cleans every tick. Test
`test_dedupe_collapses_same_hourly_target_keeps_freshest`. One-time cleanup collapsed 151→135 records
(−16 pending; 0 resolved dropped); idempotent thereafter `[CERT-live]`.

## 21.4 - The pooled cov50 "wide" alarm is an overlapping-sample illusion `[CERT-live]`

The clean live scorecard shows gaussian POOLED n=81 cov50=0.65 — apparently wide vs the 0.50 target. But over
the INDEPENDENT subset (`_independent_subset`, greedy non-overlapping) n_eff=9, cov50=0.56 and cov90=1.00; only
11% of the live forecasts are independent (`sources/probes/calibration-integrity-session-2026-08-10.md`)
`[CERT-live]`. `[INFER]` The pooled count treats 81 consecutive-15m, autocorrelated forecasts as if independent;
with a very quiet recent regime (median realized move 0.064%) price stays inside P25..P75, inflating the pooled
number. The non-overlapping backfill already measured cov50 ≈ 0.51 (`IMPROVEMENT-BACKLOG.md`). Conclusion: the
50% band is NOT miscalibrated live — the POOLED read over-states the evidence. This is the same lesson as
[Block 20] from the other side: independence (n_eff), not raw counts, is what the coverage number must respect.

## 21.5 - The improvement lead this produces `[INFER]`

`[INFER]` `calibration` already reports `n_eff` and a Wilson `cover_90_ci` over the independent subset (audit
item S7), but the 50% band still surfaces only the misleading POOLED `cover_50`. The honest, small fix: report
`cover_50` over the independent subset with its own Wilson CI, exactly as the 90% band does — so a quiet-regime
overlapping sample can no longer read as "the inner band is broken". Logged in `IMPROVEMENT-BACKLOG.md` (#21).
It changes reporting only, never the cone, in keeping with the toolkit's "measure and report, do not overfit"
discipline.

## 21.6 - Backtest corroborates the NO-TRADE default `[CERT-live]`

"How would trading the forecasts have done?" The cone is zero-drift (p_up≈0.50) → no direction. A trend proxy
(`backtest.py --rule ema_trend --hold 8 --cost-bps 1.0`, 300×15m) on the China A50 and two indices shows no
edge net of costs: CN50 full-sample CI [−4.76,+6.94] bps straddling 0 with an IS +3.22 → OOS −12.60 overfit
collapse; SPX/NAS net-negative or CI-includes-0; all thin-sample
(`sources/probes/calibration-integrity-session-2026-08-10.md`) `[CERT-live]`. This corroborates `decide.py`'s
NO-TRADE gate ([Block 8]): "trade the forecast" honestly resolves to staying flat.

## 21.7 - Connections

- **[Block 20]** - walk-forward rigor; same independence-vs-raw-count lesson, opposite direction.
- **[Block 15]** - per-market calibration ranking read from this same log (now contamination-guarded).
- **[Block 14]** - the earlier dedupe bugfix (S7) this supersedes with target-based keying.
- **[Block 8]** - the gated decision engine whose NO-TRADE the backtest corroborates.
- **IMPROVEMENT-BACKLOG #21** - the independent-subset cov50 CI reporting lead.
