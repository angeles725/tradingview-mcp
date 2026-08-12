# Block 30 - Coverage-driven single-scalar cone widener: walk-forward REJECTED out-of-sample

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> an attempt to promote the passive coverage FLAG ([Block 28]) into an ACTIVE correction — a single
> multiplicative sigma scalar `k` per `symbol|tf`, chosen with FEWER degrees of freedom than conformal
> precisely to resist the overfitting that killed the earlier corrections. It was built, tested green,
> and then REJECTED at the walk-forward honesty gate. Kept as dormant machinery, not wired on.
>
> Subject version: `analysis/forecast.py` + `analysis/cone_coverage.py` + `analysis/analyze.py` on branch
> `feat/quant-analysis-toolkit`. Session 2026-08-12.
>
> Sources: `analysis/forecast.py`, `analysis/cone_coverage.py`, `analysis/analyze.py`,
> `analysis/test_coverage_scalar.py` (local primary source). Preserved run (the decisive evidence):
> `corpus/sources/probes/coverage-scalar-gate-session-2026-08-12.md`.
> Method: read-only citation of authored code + a preserved live walk-forward measurement. `[CERT]`
> marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block. Rigor layer. NEGATIVE RESULT — the rejection is the finding.

---

## 30.1 - The idea: one knob instead of a per-quantile vector `[CERT]`

The coverage flag ([Block 28]) only WARNS that a live cone's 90% band historically under- or over-covers.
This block asked whether that same signal could actively CORRECT the cone. The design choice was
deliberately low-DoF: a single multiplicative factor `k` per `symbol|tf`, rescaling every quantile about
P50, versus conformal's per-quantile deltas. `apply_coverage_scalar` (`analysis/forecast.py:518`) scales
each quantile's distance from the median by `k` (`k>1` widens, `k<1` tightens), re-sorts the five
quantiles so the band stays monotone, and leaves P50 and `p_up` untouched — direction is never moved,
only spread `[CERT]`. `[INFER]` One parameter per group cannot bend the shape of the distribution the way
a per-quantile vector can, so it has strictly less room to memorize noise — the whole point.

## 30.2 - How `k` is fit: a split-conformal order statistic of normalized residuals `[CERT]`

`_scalar_residuals` (`analysis/forecast.py:536`) reduces each scored row to a per-side normalized residual
`u = |y - P50| / half_width`, where `half_width` is the nominal band half-width on the side the realized
close fell; `u=1` means the close landed exactly on the nominal edge `[CERT]`. `coverage_scalar_fit`
(`analysis/forecast.py:558`) then sets `k` to the `level`-quantile order statistic of those `u` values
(`conformal_delta`) — the factor that would have made the band cover its nominal level in-sample — clamped
to `[_SCALAR_K_MIN, _SCALAR_K_MAX]` = `[0.5, 3.0]` (`analysis/forecast.py:515`) and returning `None` below
`min_n` scored rows `[CERT]`. `[INFER]` This is the same conformal machinery already trusted for the band
deltas, reused on a scalar instead of a vector.

## 30.3 - The honesty gate is built INTO the module `[CERT]`

`coverage_scalar_validate` (`analysis/forecast.py:576`) is a walk-forward mirror of `conformal_validate`
(`analysis/forecast.py:420`): it sorts rows by `made_at`, fits `k` on the FIRST `train_frac` (default 0.7),
and MEASURES raw vs `k`-scaled coverage of the band on the held-out remainder, returning
`cover_raw_test` / `cover_adj_test` `[CERT]`. `[INFER]` The generalization test is not an afterthought
bolted on for this probe — it ships as a first-class function beside the fit, so the module can never be
used without its own out-of-sample check available.

## 30.4 - The wiring: fit-map builder and a guarded, default-off flag `[CERT]`

`build_scalar_map` (`analysis/cone_coverage.py:91`) groups the scored cone backfill by `symbol|tf`, fits `k`
on `REF_MODEL` (`gaussian`, `analysis/cone_coverage.py:32`) at the 90% band, and omits groups below `min_n`
so a thin tail can never mint a factor `[CERT]`. `load_scalar_map` (`analysis/cone_coverage.py:82`) returns
an empty dict when the artifact is absent — absent map => no rescale `[CERT]`. In `analyze.py` the
`--coverage-scalar` flag defaults to `None` (`analysis/analyze.py:97`) and the rescale runs ONLY when a
path is passed and an entry with `k != 1.0` exists (`analysis/analyze.py:239`) `[CERT]`. `[INFER]` Default
`analyze.py` behavior is unchanged; the correction is opt-in and inert unless explicitly invoked.

## 30.5 - Tested green — TDD, 12 tests `[CERT]`

`analysis/test_coverage_scalar.py` holds 12 tests, all passing `[CERT]`: identity at `k=1`
(`test_apply_scalar_k1_is_identity`, `:47`), symmetric widening about the median (`:55`), preserved
monotone order (`:66`), `k>1` recovered on a too-tight sample (`:76`), `k≈1` on a calibrated sample (`:92`),
the `[0.5, 3.0]` clamp (`test_fit_is_clamped`, `:112`), `None` below `min_n` (`:106`), the walk-forward
adj-beats-raw case (`test_validate_adj_beats_raw_on_too_tight`, `:123`), and the map builder's grouping /
thin-group omission / absent-map behavior (`:148`, `:161`, `:167`) `[CERT]`. `[INFER]` The machinery is
correct as specified — green tests prove the code does what it claims, not that the correction helps.

## 30.6 - The walk-forward verdict: improved 0, harmed 2 `[CERT-live]`

Run over the real cone backfill — 1804 scored rows, 30 `symbol|tf` groups, `n` 47-77 each — fitting `k` on
the first 70% by `made_at` and measuring raw vs `k`-scaled 90%-band coverage on the held-out 30%:
**improved = 0, harmed = 2** (`coverage-scalar-gate-session-2026-08-12.md`) `[CERT-live]`. The two harmed
groups were both TIGHTENED by a `k<1` fit on a noisy train split: `HK33HKD|M` `k=0.72` drove test cover90
`0.91 -> 0.74`, and `WTICOUSD|W` `k=0.78` drove it `0.89 -> 0.83` — the scalar squeezed already-fine cones
below nominal out-of-sample `[CERT-live]`. Not one group was moved from too-tight to well-covered.

## 30.7 - Why it did nothing where it was needed — and was absent where it mattered most `[CERT-live]`

The groups that were genuinely too-tight OOS stayed that way: `JP225|W` (0.78), `NAS100|W` (0.78),
`NAS100|M` (0.82/0.86) `[CERT-live]`. Their TRAIN splits were NOT too-tight, so the fit came back `k≈0.94`
and did essentially nothing — the miscoverage appeared only in the test half. And the METALS that motivated
the whole flag — XAU/XAG — are ABSENT from the pool entirely (`total scored: 1804 | groups: 30 |
XAU/XAG present?: ABSENT`) `[CERT-live]`. `[INFER]` The correction could not have helped the very
instruments it was meant for, and applying a factor fit on indices/FX to the absent metals would be pure
extrapolation — the exact trap.

## 30.8 - VERDICT: NO-SHIP, kept dormant `[INFER]`

`[INFER]` The method was principled — 1 parameter per group against conformal's per-quantile vector, chosen
to reduce overfitting — and it STILL failed to generalize, because the miscoverage is not structurally
stable across the chronological split. This is the same failure class as the conformal 50%-band ([Block 20])
and ACI ([Block 22]) OOS-overfit results, and this session's other honest negatives ([Block 26], [Block 27]).
Decision: NO-SHIP. The code stays tested and green but DORMANT (exactly like the `adaptive=True` ACI path
noted at `analysis/forecast.py:609`); no `cone-coverage-scalar.json` artifact was written — deliberately —
so `load_scalar_map` returns empty and `analyze.py` is unchanged unless `--coverage-scalar` is explicitly
passed. The coverage FLAG ([Block 28]) remains the honest shipped posture.

## 30.9 - The standing lesson `[INFER]`

`[INFER]` At `n ≈ 50-80` per group, per-group coverage corrections overfit — even a single-scalar one with
minimal DoF. A diagnostic FLAG that describes a group's historical coverage beats a fragile auto-correction
that fits noise on one half of the timeline and pays for it on the other. Fewer degrees of freedom bought
resistance, not immunity; the honest move is to warn and let the reader widen judgment manually, not to
auto-rescale a cone the data cannot yet justify correcting.

## 30.10 - Connections

- **[Block 28]** - the passive coverage flag this block tried, and failed, to upgrade into an active
  correction; it remains the honest shipped posture.
- **[Block 20]** - the conformal 50%-band correction, first of this OOS-overfit lesson.
- **[Block 22]** - the ACI walk-forward rejection; same failure class, and the dormant-machinery precedent
  this block follows.
- **[Block 26]**, **[Block 27]** - the broader lineage of this session's honest negatives
  (block-bootstrap, vol-floor).
