# Block 14 - Tier-2 refinements: CRPS, a dedupe bugfix, gold hygiene, and GJR rejected on evidence

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> the cheap, evidence-backed refinements after the conformal work — a full-distribution CRPS score, a latent
> calibration bug fixed, the fragmented gold key unified, and a GJR-GARCH leverage estimator investigated
> and REJECTED because the backfill A/B showed no improvement.
>
> Subject version: `analysis/forecast.py`, `analysis/quant.py`, `analysis/test_forecast.py`,
> `analysis/test_quant.py` committed `793740b`; the gold migration in `corpus/forecasts.jsonl` committed
> `cfdc3b8`. Branch `feat/quant-analysis-toolkit`. Session 2026-08-10.
>
> Sources: the files above (local primary source). Preserved run:
> `sources/probes/tier2-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session TDD + backfill A/B.
> `[CERT]` marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit
> deduction. METHODOLOGY/DESIGN block.
>
> Refinement layer. Complements [Block 12]'s pinball with CRPS, hardens [Block 9]'s store, and closes the
> GJR question the methods research ([Block via the three-agent survey]) left open.

---

## 14.1 - CRPS: one number for full-distribution calibration `[CERT]`

The calibration report already tracked per-quantile pinball; `crps_from_quantiles` adds the Continuous
Ranked Probability Score, approximated as 2x the trapezoid integral of the pinball loss over the stored
levels (`analysis/forecast.py:120`). It is attached per model in `score_record`
(`analysis/forecast.py:164`) and surfaced as `mean_crps_bps` in `stats` (`analysis/forecast.py:250`).
`[INFER]` CRPS weights by the tau-spacing that the flat mean-pinball ignores, so it is a strictly-proper
single summary of the WHOLE predictive distribution — a better cross-model ranking than coverage (which a
merely-wider cone always "wins").

## 14.2 - A latent dedupe bug that silently dropped outcomes `[CERT]`

`_dedupe` collapses duplicate forecasts (same symbol/tf/made_at/horizon) and `calibration` calls it on every
read. It was last-wins, so an unscored re-record of a bar could OVERWRITE the scored copy and lose the
realized outcome. The fix keeps a SCORED copy over an unscored one, last-wins only among equal status
(`analysis/forecast.py:182`). `[INFER]` This is a real calibration-integrity fix, not cosmetic: coverage and
pinball are computed over the deduped set, so a dropped score was an undercount. It surfaced only because a
data migration (14.3) exposed the loss.

## 14.3 - Unifying the fragmented gold key `[CERT-live]`

The store carried gold under two keys — `OANDA:XAUUSD` and a legacy bare `XAUUSD` (pre prefix-convention) —
splitting the toolkit's largest sample ([Block 11] flagged this). The 7 bare records were re-keyed and the
log de-duplicated with the fixed dedupe: 81 -> 51 unique records, 29 scored, 0 bare
(`sources/probes/tier2-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` The 81->51 collapse is exact
duplicates removed, not data lost: every unique key that had a scored copy kept it (29 scored preserved),
which is exactly what the 14.2 fix guarantees.

## 14.4 - GJR-GARCH: investigated, then rejected on the A/B `[CERT]` / `[CERT-live]`

`gjr_garch11_vol` adds a leverage term (negative returns raise next-bar variance more) with Student-t
innovations and variance targeting (`analysis/quant.py:709`) — the asymmetric refinement the methods
research named. A backfill A/B over 778 store windows compared a GJR-blend cone against the symmetric-GARCH
blend: pooled pinball 3.530 vs 3.531, identical cov90 (0.920) and cov50 (0.620), and per-symbol deltas
within +-0.5% (`sources/probes/tier2-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` No measurable gain —
the GJR sigma is diluted 50% by the HAR blend, the leverage asymmetry is small at 15m/1h, and a zero-drift
symmetric cone barely changes with an asymmetric vol estimate. With the GJR 4-parameter fit costing ~3-4x
GARCH per call, wiring it would slow every tick for nothing. Decision: keep the function available and
tested, but do NOT wire it — evidence-based non-adoption, like the adaptive-vol and gold-tail calls.

## 14.5 - Connections

- **[Block 12]** - the pinball/coverage report CRPS now complements; the blend that dilutes GJR's effect.
- **[Block 11]** - the dual-gold-key hygiene item this closes.
- **[Block 9]** - the persistent store whose integrity the dedupe fix protects.
- **[Block 13]** - the backfill machinery reused for the GJR A/B.
