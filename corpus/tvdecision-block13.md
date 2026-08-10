# Block 13 - Activating the conformal layer: a shared cone recipe and a backfill-seeded correction

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how the [Block 12] conformal calibration layer was turned from built-but-inert into LIVE — by (1) removing
> a cone-definition DRIFT between the live and backtest paths via a single shared recipe, and (2) seeding the
> correction table from a store-driven backfill so it reaches min_n immediately instead of after weeks of
> live maturations.
>
> Subject version: `analysis/quant.py`, `analysis/analyze.py`, `analysis/backfill.py`,
> `analysis/forecast.py`, `analysis/collect-hook.sh` committed `89aa22e` on branch
> `feat/quant-analysis-toolkit`. Session 2026-08-10.
>
> Sources: the five files above plus `analysis/test_quant.py` (local primary source). Preserved run:
> `sources/probes/conformal-activation-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session backfill validation + TDD.
> `[CERT]` marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit
> deduction. METHODOLOGY/DESIGN block.
>
> Activation layer. Makes [Block 12]'s correction real, on the evidence of an [Block 9]-store backfill.

---

## 13.1 - The A/B that justified activation `[CERT-live]`

A backfill A/B over 778 non-overlapping historical forecasts across 10 markets showed the [Block 12] blended
cone is marginally better on pinball than the old GARCH/EWMA cone (pooled 3.531 vs 3.574), that cov90 is
already ~nominal out-of-sample (0.91), and that the real, systematic defect is an OVER-DISPERSED 50% band
(~0.60 vs 0.50) in BOTH cones (`sources/probes/conformal-activation-session-2026-08-10.md`) `[CERT-live]`.
`[INFER]` So the highest-value move was not a new model but ACTIVATING the correction that fixes exactly
that — the conformal layer already built and tested.

## 13.2 - The drift bug: two cones that claimed to be one `[CERT]`

`backfill.py`'s `_cones` was documented as building the cone "exactly as analyze.py" but had silently
DRIFTED: it used the old GARCH/EWMA-on-returns sigma and `backfill_bars` extracted only the close. `[INFER]`
The root cause is duplication — the cone-sigma recipe lived in two files, so an upgrade to one (the HAR blend
in [Block 12]) left the other stale. A backtest that does not build the SAME cone as production measures the
wrong thing.

## 13.3 - One recipe, two callers `[CERT]`

The fix is a single source of truth: `quant.cone_sigma(v_garch, o, h, l, c, ret)` blends the caller's GARCH
sigma with a HAR-RV forecast over a Rogers-Satchell series and falls back to EWMA, returning
`(sigma, v_har)` (`analysis/quant.py:771`). `analyze.py` calls it (`analysis/analyze.py:128`) and so does
`backfill.py`'s now OHLC-aware `_cones` (`analysis/backfill.py:39`, `analysis/backfill.py:68`). `[INFER]`
The GARCH fit stays in the caller because it is expensive; only the blend recipe is shared — enough to make
drift structurally impossible without re-duplicating the fit.

## 13.4 - Reaching min_n without waiting: --extra-log `[CERT]`

The conformal table needs enough matured forecasts per `symbol|tf|horizon` group, and the live log is far
below that. `forecast.py conformal` gained `--extra-log` (`analysis/forecast.py:452`), which POOLS extra
logs with the live log before computing corrections (`analysis/forecast.py:473`). `[INFER]` A store-driven
backfill — deterministic, non-overlapping, honestly scored against known future closes — is a legitimate
seed: it is the same instrument, the same cone (13.3), just historical rather than forward.

## 13.5 - The hook closes the loop, rate-limited `[CERT]`

The collection hook now refreshes the backfill seed only when it is missing or older than
`BACKFILL_MAX_AGE` (12h, since it is GARCH-heavy and deterministic from the store)
(`analysis/collect-hook.sh:60`, `analysis/collect-hook.sh:109`, `analysis/collect-hook.sh:111`), then
computes `conformal.json` from the live log POOLED with that seed
(`analysis/collect-hook.sh:113`). `analyze --conformal` already consumes the table ([Block 12]), so each
recorded cone carries the correction. `[INFER]` Ordering holds: the seed and table are refreshed AFTER
scoring, so a tick records with the prior table and re-derives it for the next.

## 13.6 - What it does live, and the honest caveat `[CERT-live]` / `[INFER]`

Seeded from live+backfill, the table populates all 10 groups (n>=64), and on gold `analyze --conformal`
widens the under-covered 90% band and tightens the over-dispersed 50% band, leaving P50/p_up untouched
(`sources/probes/conformal-activation-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` The honest limit:
the correction is seeded from STORE HISTORY, not pure forward-testing, and the coverage-after in the A/B is
measured on the calibration set (the guarantee is marginal on exchangeable data). It is sound bootstrapping
that the live loop keeps refining — not coverage earned in real time. The generated `conformal.json` and
`forecasts-backfill.jsonl` are gitignored artifacts.

## 13.7 - Connections

- **[Block 12]** - the conformal layer this activates; the blended cone the shared recipe centralizes.
- **[Block 9]** - the persistent store the backfill seed is drawn from.
- **[Block 10]** - the collection hook that now refreshes the seed and the correction table.
- **[Block 11]** - the gap-robust Rogers-Satchell vol the shared recipe carries into the backtest.
