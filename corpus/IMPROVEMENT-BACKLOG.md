# Quant Toolkit — Improvement Backlog

> Forward-looking audit of `analysis/` (quant/backtest/decide/collect/analyze). Distinct from the
> closed capability-hardening + tvdecision document outline. Ranked by impact on statistical validity.
> Certainty markers: `[CERT]` verified against local source this session · `[INFER]` method-level
> deduction not line-verified.

## Verified against source (spot-checked 2026-08-07)

- **#6 SELL rule mismatch [CERT]** — `decide.py:107-108`. `rule_ema_trend` emits a long signal (`c>ema`);
  `simulate(..., direction=-1)` only flips P&L sign. Gate B for a SELL therefore tests "short when price is
  ABOVE its EMA" — a counter-trend signal. Fix: mirror the condition to direction (`c<ema` for shorts).
- **#4 verdict uses i.i.d. CI, not block CI [CERT]** — `backtest.py:137,143` vs `194`. `compute_stats`
  decides `edge` from `bootstrap_mean_ci` (i.i.d., narrower); the honest `bootstrap_mean_ci_block` is only
  printed in `main()`. Fix: gate the verdict (and Gate B) on the block-bootstrap CI, or require both.
- **#5 lookahead in `simulate_process` [CERT]** — `decide.py:164-175`. `edge_override` computed once on
  `bars[:cut]` (60%) is applied for every `t>=warmup(~46)`, so `t<cut` uses future bars `[t,cut)`. Fix:
  expanding-window edge that only sees `bars[:t]`, or start the walk at `cut`. Add a regression test.
- **#2 `scale_sigma` contradicts the VR gate [CERT]** — `quant.py:328` returns `σ·√h` (RW, VR=1), but Gate A
  only trades when VR>1, where √h understates horizon vol → stop too tight, size too large. Fix:
  `σ_h = σ₁·sqrt(h·VR(h))`.

## P1 — high impact (statistical validity)

| # | Axis | Anchor | Weakness | Fix | Effort/Payoff |
|---|---|---|---|---|---|
| ~~1~~ | numerical-method | `quant.py:56-87` `ols_trend` | OLS of price *level* on time = spurious regression (unit root); Gate A fires on noise [CERT: 64% false-positive on random walks] | **DONE 2026-08-07** — (a) `newey_west_lrv` HAC SE for the slope; (b) VERIFIED HAC alone insufficient for I(1) (still 64%), so also gate `significant` on the STATIONARY drift (mean log-return t-test) → spurious rate 64%→5.2%, genuine trends kept. Tests: `test_newey_west_lrv_inflates_under_autocorrelation`, `test_ols_trend_hac_widens_ci_on_autocorrelated_residuals`, `test_ols_trend_rejects_spurious_random_walk_trend` | M / high |
| ~~2~~ | numerical-method | `quant.py:328` `scale_sigma` | √h scaling inconsistent with VR>1 trading regime [CERT] | **DONE 2026-08-07** — `scale_sigma(σ,h,vr)` = `σ·sqrt(h·vr)`, degenerate-VR fallback to √h; `decide.py` passes `variance_ratio(ret,horizon)`; test `test_scale_sigma_uses_variance_ratio` | S / high |
| ~~3~~ | procedure | `analyze.py:131-136` | 6 simultaneous conditionals at α=0.05 → FWER ≈ 26% [CERT] | **DONE 2026-08-07** (conditionals) — `benjamini_hochberg` + `correct_conditionals` (BH-FDR) re-label verdicts, `p_adjusted` + `conditionals_correction` in report; tests `test_benjamini_hochberg_matches_reference`, `test_conditionals_multiple_testing_correction`. **Still open:** rule×hold×period sweep selection bias → Deflated Sharpe (ties #13) | S / high |
| ~~4~~ | backtest-honesty | `backtest.py:137,143` vs `194` | verdict driven by i.i.d. CI, not the block CI it computes [CERT] | **DONE 2026-08-07** — `compute_stats` now uses `bootstrap_mean_ci_block` for both `ci95_ret` and verdict; Gate B inherits it; test `test_verdict_uses_block_bootstrap_ci_not_iid` | S / high |
| ~~5~~ | backtest-honesty | `decide.py:164-175` | in-sample edge precondition leaks future into `t<cut` [CERT] | **DONE 2026-08-07** — extracted `_edge_precondition(...,t,...)` using `bars[:t]` only, refreshed every `refit` bars; tests `test_edge_precondition_ignores_future_bars`, `test_simulate_process_runs_without_lookahead` | M / high |

## P2 — medium impact (decision logic & method choice)

| # | Axis | Anchor | Weakness | Fix | Effort/Payoff |
|---|---|---|---|---|---|
| ~~6~~ | decision-logic | `decide.py:107-108` | SELL tests a counter-trend long signal [CERT] | **DONE 2026-08-07** — `rule_ema_trend` now direction-aware (`c<e` for shorts); `decide.py` passes direction; test `test_ema_rule_mirrors_condition_for_short` | S / high |
| ~~7~~ | algorithm | `decide.py:97`; `quant.py:183-201` | `vr>1.0` hard threshold, no significance [CERT] | **DONE 2026-08-07** — `variance_ratio_test` (Lo–MacKinlay M2 het-robust z, p); Gate A now requires `vr>1 AND z>=cfg.vr_z(1.645)`; gold shows VR4=0.87 z=−1.10; test `test_variance_ratio_test_calibrated_and_detects_momentum` | M / med |
| ~~8~~ | decision-logic | `decide.py:125-134` | Gate C target = zero-drift cone quantile ⇒ ~0 EV; ignores stop-vs-target hit probability [CERT] | **DONE 2026-08-07** — `quant.barrier_hit_probabilities` (MC first-passage p_target/p_stop); Gate C now requires `rr>=min_rr AND EV = p_target·reward − p_stop·risk > 0`; detail shows P(tgt)/P(stop)/EV; test `test_barrier_hit_probabilities` | M / med |
| ~~9~~ | backtest-honesty | `backtest.py:151-160` `walk_forward` | single 60/40 split, no purge/embargo; trade at boundary leaks across cut [CERT] | **DONE 2026-08-07** — purge IS signals whose trade window crosses the cut + embargo the first `hold` OOS bars; test `test_walk_forward_purges_boundary_trades`. (Full rolling/anchored WF still a further enhancement) | M / med |
| ~~10~~ | numerical-method | `quant.py:281-323` `garch11_vol` | Gaussian MLE on fat tails biases α/β; Nelder–Mead fragile; loose success check; untested [CERT] | **DONE 2026-08-07** — Student-t innovations (df estimated), variance targeting (ω=var·(1−α−β), 3 params), multi-start, drops the loose success check; params now include `nu`; gold fits ν≈4.4; test `test_garch_recovers_persistence_with_student_t` | M / med |
| ~~11~~ | data-capture | `collect.py:63-79` `merge` | no session/overnight gap detection → giant cross-gap "returns" inflate σ, distort GARCH/VR [CERT: 3-5 gaps in live gold 15m] | **DONE 2026-08-07** — `log_returns(closes, times, gap_tol)` drops cross-gap returns; analyze/decide capture `time` and pass it; `collect.py --stats` shows a contiguity report; tests `test_log_returns_excludes_cross_gap`, `test_contiguity_counts_session_gaps` | M / med |
| ~~12~~ | forecast | `quant.py:404-426` `mc_student_t` | no `df>2` guard → infinite-variance blowup on ~280 pts [CERT] | **DONE 2026-08-07** — guard `df<=2`/non-finite/`scale<=0` → bootstrap-cone fallback, reports degenerate df; test `test_mc_student_t_guards_degenerate_df` (scipy venv) | S / med |
| ~~13~~ | algorithm | `backtest.py:74-88` | no Sharpe / Deflated Sharpe / max drawdown [CERT] | **DONE 2026-08-07** — `quant.max_drawdown`, `quant.probabilistic_sharpe` (Bailey-LdP, skew/kurtosis-aware); `BTStats` gains `sharpe`/`psr`/`max_drawdown`, shown in backtest output; tests `test_max_drawdown_and_probabilistic_sharpe`, `test_compute_stats_reports_sharpe_psr_drawdown`. Deflated-SR (needs #trials from sweep) still open, ties #3 | M / med |
| ~~14~~ | numerical-method | `quant.py:116-176` | percentile bootstrap under-covers for skewed mean [CERT] | **DONE 2026-08-07** — `bca_ci` (bias-correction z0 + jackknife acceleration); `bootstrap_mean_ci_block` now BCa-corrected (still serial-dependence-aware, drives the verdict); test `test_bca_ci_symmetric_matches_percentile_and_shifts_on_bias` | M / low-med |

## P3 — hygiene

| # | Axis | Anchor | Weakness | Fix | Effort/Payoff |
|---|---|---|---|---|---|
| ~~15~~ | numerical-method | `quant.py:248` | EWMA seeded by single squared return, no de-mean [CERT] | **DONE 2026-08-07** — seed = mean(r²) over warm-up window (uncentered, matches the IGARCH recursion); test `test_ewma_seed_uses_warmup_window_not_single_return` | S / low-med |
| ~~16~~ | forecast | `quant.py:364-372` | reported cone `mean` is Jensen-biased above median [CERT] | **DONE 2026-08-07** — key renamed `mean`→`mean_lognormal` with a comment that it is not an expected move; median/band remain the guidance (key was unused by display/forecast) | S / low |
| ~~17~~ | tooling | `quant.py:90-96,241-323` | O(n²) Theil–Sen + pure-Python GARCH/EWMA don't scale with growing store [CERT] | **DONE 2026-08-07** — `theilsen_slope` subsamples up to `max_pairs` random pairs past the O(n²) budget (unbiased, bounded cost); test `test_theilsen_exact_and_subsampled`. GARCH/EWMA O(n) loops left as-is (fine to several thousand bars) | M / low-med |
| ~~18~~ | data-capture | `collect.py:63-79` | no OHLC integrity check (`h>=max(o,c,l)`); poisons Parkinson/GK (`log(h/l)`) [CERT] | **DONE 2026-08-07** — `valid_ohlc(b)` (finite, positive, `h>=max(o,c,l)`, `l<=min(o,c,h)`); `main` filters invalid bars before merge and reports rejects; test `test_valid_ohlc_predicate` | S / low-med |
| ~~19~~ | test-coverage | `test_quant/backtest/decide.py` | gaps on the fragile numerics [CERT] | **DONE 2026-08-07** — suite grew 28→58; added tests for GARCH persistence, mc_student_t df guard, scale_sigma/VR, walk_forward purge, simulate_process lookahead, VR significance, block-CI verdict wiring, BCa, barrier probs, gap-aware returns, OHLC validity, and Parkinson/Garman-Klass/c2c reference formulas | M / med |

## Already correct — do NOT redo
- No-lookahead fills in `backtest.simulate` (next-open entry, `exit_i>=n` drop), tested.
- Non-overlapping trades by default; Politis–Romano stationary block bootstrap (`quant.py:137-176`);
  Wilson score intervals (`quant.py:432-443`).
- Per-side/gross-vs-net costs; zero-drift cones; conditional lookahead guard test (`test_analyze.py`).

## Delivered beyond the audit (user-requested)
- **Forecast calibration tooling — DONE 2026-08-07.** New `analysis/forecast.py` (stdlib):
  `record` (log a cone forecast from an analyze --json report), `score` (match matured forecasts to
  realized closes and record 90%/50% band hits), `stats` (per-model coverage — evidence for whether the
  cone is well-calibrated). Log: `corpus/forecasts.jsonl`. Tests: `test_forecast.py` (5). analyze report
  now carries `last_bar_unix` + `bar_step_sec` so forecasts are self-contained. `collect-hook.sh` extended
  to record + score every throttled tick, so the calibration record accumulates automatically.

## Discovered during audit (not in original 19)
- **#20 `analyze.py --json` was completely broken [CERT] — FIXED 2026-08-07.** `Trend.significant` was a
  `np.bool_` (not a subclass of Python `bool`; `__name__` is `'bool'` under numpy 2.x but `type() is bool`
  is False), which `json.dumps` cannot serialize → the machine-readable report (what the pipeline consumes)
  raised `TypeError` and emitted nothing. Fix: `bool(...)` at `quant.py:86`. Test:
  `test_trend_significant_is_json_serializable_bool`. Same class of latent bug as the scipy-venv gap: an
  untested path silently non-functional. Found via an end-to-end smoke, not unit tests.

## Testing procedure (IMPORTANT)
The base `python3` has **no scipy**, so `python3 -m pytest` runs all scipy-dependent code
(GARCH `optimize`, `mc_student_t`, HAC/`t.ppf`) in its `_HAS_SCIPY=False` fallback — those paths are
NEVER exercised and scipy-guarded tests early-return, giving false green. Run the real suite with the
scipy venv, which lacks pytest, via each file's standalone runner:
```
VENV=~/.local/share/research-sdd-tools/venv/bin/python3   # scipy 1.18, numpy 2.5
for f in analysis/test_*.py; do "$VENV" "$f"; done
```
Fixes touching scipy paths (#10 GARCH, #12, #1 HAC) MUST be validated this way. Adding pytest to the
venv (or a `make test` that uses it) is itself a P3 procedure improvement.

## Calibration evidence (backfill, 2026-08-07)
`analysis/backfill.py` walks NON-OVERLAPPING windows over the 479-bar gold store, forecasts from `bars[:t]`
only (no lookahead, same zero-drift cones as analyze), and scores vs the realized close at t+h — an independent
calibration sample without waiting for live forecasts.

| horizon | n | cover90 (target 0.90) | cover50 (0.50) | best pinball |
|---|---|---|---|---|
| 1h (h=4) | 104 | gaussian 0.82 / boot 0.80 / t 0.82 (CI ~[0.73,0.88]) | gaussian **0.51** / boot 0.44 / t 0.45 | **gaussian** 3.100 |
| 2h (h=8) | 52 | gaussian 0.87 / boot 0.85 / t 0.88 | ~0.42–0.46 | ~tied |

**Findings (evidence-based):** (1) the **90% band UNDER-COVERS** (~81% at 1h, ~87% at 2h vs 90%) → cones a
touch too narrow in the tails / horizon vol slightly underestimated, worse at 1h. (2) the **50% band is
well-calibrated** (gaussian 0.51). (3) the **GAUSSIAN cone wins** pinball at n=104 — the fat-tail models don't
help on gold 15m; simpler is better here. Backfill logs are regenerable backtest records (untracked).

**Diagnosis of the 90% under-coverage (attacked 2026-08-07 — NEGATIVE result, do not overfit):**
- Tested alternative cones — a zero-drift **block-bootstrap** cone (serial-dependence) and an **empirical h-bar
  return** cone — both still cover ~0.80–0.82. So it is **NOT a cone-shape problem** (gold 15m is currently
  mean-reverting, VR<1, so serial-dependence widening does not apply). Root cause = **non-stationary vol**:
  historical dispersion underestimates future tail dispersion.
- Tested a **fixed widening factor** with a train/validate split: k≈1.30 hits 90% on the calibrate half but
  **over-covers (98%) on the validate half** (the two halves differ, 77% vs 88% base coverage) → a constant
  multiplier **does not generalize** (overfits the calibration regime).
- **Conclusion:** no static fix (cone shape or fixed multiplier) robustly corrects it. Honest remedies are
  ADAPTIVE (regime-aware vol) or simply REPORTING the realized coverage so the nominal 90% band is read as its
  measured ~82%. Not shipping a fabricated "fix". `analysis/backfill.py` lets this be re-measured anytime.

**Cross-symbol evidence (2026-08-07, 59 windows each, h=4) — the under-coverage is GOLD-SPECIFIC, not systemic:**

| symbol | cover90 (target 0.90) | cover50 (0.50) |
|---|---|---|
| gold (recent) | **0.82** (under) | 0.44–0.51 |
| EURUSD | 0.92 | 0.75 (over) |
| BTCUSDT | 0.90–0.95 | 0.54 (good) |
| SPX500 | 0.95–0.97 | 0.68 (over) |

- EURUSD / BTC / SPX are well-calibrated or OVER-cover → a **global widening would break them** (push to ~0.98).
  This confirms the fix must be **per-symbol / regime-adaptive**, and that gold's recent window was an unusual
  high-tail-move period. Reporting realized coverage per symbol is the pragmatic honest path.
- **Method gap found:** pinball loss is in PRICE units (BTC ~42, gold ~3, EURUSD ~0.000) → NOT comparable across
  symbols/horizons. Normalize (per S0 / in bps) for cross-symbol model ranking. *(new method item)*

## Post-audit tooling (Tasks #2/#4 + method, 2026-08-07)
- **Realized-coverage reporting (Task #2, DONE):** `forecast.coverage_table` + `forecast.py calibrate` →
  `calibration.json`; `analyze.py --calibration` annotates the cone with its measured 90%/50% coverage for the
  symbol/horizon (honest — never changes the model).
- **Pinball normalization (method, DONE):** raw pinball is in PRICE units (gold 7.4 vs EURUSD 1.2 vs BTC 6.5 bps
  when normalized; raw was 3/0/42 — meaningless). `score_record` now also stores `pinball_bps` (per S0); `stats`
  ranks cones by `mean_pinball_bps`, comparable across symbols/horizons. Test `test_pinball_bps_is_scale_invariant`.
- **Multi-symbol accumulation (Task #4, DONE):** `collect-hook.sh` takes a `SYMBOLS` array (default just gold →
  unchanged); with >1 it cycles the chart per symbol (settle+pull+collect+record+score) and restores the primary.
  Builds live calibration across instruments. Opt-in, non-intrusive by default.

## Adaptive-vol investigation (Task #3, 2026-08-07 — NO CHANGE warranted)
Tested whether a better/adaptive horizon vol fixes the under-coverage. Out-of-sample (validate) cover90 of a
gaussian cone, close-to-close (EWMA) vs Garman-Klass RANGE vol:

| symbol | n | cover90 close | cover90 GK |
|---|---|---|---|
| gold | 105 | 0.88 | 0.88 |
| EURUSD | 59 | 0.92 | 0.92 |
| SPX | 59 | 0.96 | 0.92 |
| BTC | 59 | 0.92 | 0.92 |

**Conclusion:** on recent / out-of-sample data the cones are ALREADY well-calibrated (0.88–0.92); gold's
full-sample 0.82 was a past high-vol regime, not persistent (recent gold = 0.88). GK-vol shows no clear gain
(e.g. SPX 0.96→0.92 is ~1 forecast at n≈23 — noise). **No adaptive-vol change is justified by the evidence** —
adding one would be the overfit we keep refusing. The honest surface is the realized-coverage report (Task #2).

## Second-pass audit (2026-08-07, after the 20-item hardening)
Fresh findings NOT in the DONE rows above. Ranked by impact on the go/no-go decision.

### P1 — correctness bugs biasing the decision
- ~~**S1**~~ **[CERT] DONE 2026-08-07** long-only edge precondition — `_edge_precondition` now derives
  `direction` from `ols_trend(c[:t]).slope` and passes it to `rule_ema_trend` + `simulate`; detail shows
  `dir=`. Test `test_edge_precondition_direction_follows_slope`. **S / high**
- ~~**S2**~~ **[CERT] DONE 2026-08-07** — exit logic extracted to `_resolve_exit`; gap-through stops fill at
  `min(o[k],stop)` (long) / `max(o[k],stop)` (short); intrabar touches still fill at the level.
  Test `test_resolve_exit_gap_through_fills_worse`. **S / high**
- ~~**S3**~~ **DONE 2026-08-07** — `_resolve_exit` applies adverse `slip` to STOP (market) fills, not targets
  (limit); `Config.cost_bps`/`slip_frac` added; Gate B uses `cfg.cost_bps` (no longer hardcoded 1.0);
  `simulate_process` passes `cfg.slip_frac`. Defaults conservative (knob exposed; set gold-realistic values).
  Test `test_resolve_exit_applies_stop_slippage`. **M / high** (spread/slippage per-side in backtest.simulate CLI still tunable)
- ~~**S4**~~ **[CERT] DONE 2026-08-07** GARCH refit every bar — `decide` gained `sigma_override`;
  `simulate_process` fits GARCH once per `refit` window and passes it, throttling O(n) fits to O(n/refit).
  Test `test_decide_sigma_override_skips_garch`. **M / med-high**

### P2 — methodology & robustness
- ~~**S5**~~ **DONE 2026-08-07** — `barrier_hit_probabilities` now takes OHLC and resamples bars jointly as
  (close-return, high/low excursion), testing intrabar touches; a bar spanning both barriers is charged to the
  STOP (conservative). Gate C passes OHLC. Tests `test_barrier_hit_probabilities`, `test_barrier_intrabar_raises_stop_probability`. **M / high**
- ~~**S6**~~ **DONE 2026-08-07** — `forecast.pit` (piecewise-linear CDF from the 5 quantiles) and
  `forecast.pinball_loss` (strictly-proper quantile loss); `score_record` stores per-model `pit`/`pinball`;
  `calibration` + `stats` report `mean_pinball` to rank the cones. Test `test_pit_and_pinball_scoring_rules`. **M / med-high**
- ~~**S7**~~ **DONE 2026-08-07** — `_dedupe` (by symbol/tf/made_at/horizon), `_independent_subset` (greedy
  non-overlapping → `n_eff`), `_wilson`; `calibration` reports `n_eff` and a `cover_90_ci` over the independent
  subset; `stats` shows both. Test `test_dedupe_effective_n_and_wilson`. **S-M / med-high**
- ~~**S8**~~ **[CERT] DONE 2026-08-07** — `_position_size` caps size at `max_leverage*equity/entry` (Config.max_leverage=10);
  when the cap binds, reported `risk_cash = size*risk`. Test `test_position_size_leverage_cap`. (fractional Kelly still optional) **S-M / med-high**
- ~~**S9**~~ **[CERT] DONE 2026-08-07** — `barrier_hit_probabilities` now draws paths via `stationary_bootstrap_indices`
  (inherits momentum) instead of i.i.d. `rng.integers`. Test `test_barrier_uses_block_bootstrap`. **M / med**
- ~~**S10**~~ **[CERT] DONE 2026-08-07** (VR) — `_return_segments` + `variance_ratio`/`variance_ratio_test` take `times`
  and pool k-sums / autocovariances only WITHIN contiguous sessions; decide passes raw returns + times. Test
  `test_variance_ratio_segments_across_gaps`. GARCH recursion-reset-at-gaps still a further refinement. **M / med**
- ~~**S11**~~ **DONE 2026-08-07 (edge-aware Gate C, user-approved).** Finding: Gate C scored EV on a ZERO-DRIFT
  cone, ignoring the directional edge Gate A found → EV≈0 martingale (engine only traded via the stop/target
  model mismatch). Naive "both barriers from one cone" FAILS: under strong drift the cone P25 sits above entry →
  no definable stop. Sound fix: the STOP stays a vol-based risk-control level (keeps #2/S4), while the TARGET and
  the EV come from ONE edge-aware cone — `quant.mc_block(..., drift_zero=False)` (drift + block momentum) and
  `barrier_hit_probabilities(..., drift_zero=False)`. EV now reflects the real edge (positive on a genuine trend)
  and is internally consistent. Tests `test_mc_block_wider_than_iid_under_momentum`,
  `test_mc_block_drift_makes_cone_edge_aware`. **S-M / med**
- ~~**S12**~~ **DONE 2026-08-07** — `_dir_hit` returns None unless `|p_up-0.5|>DIR_EPS(0.03)` and non-tie;
  `calibration` reports `dir_acc`/`dir_n` only over directional records (n/a otherwise); stats print updated.
  Test `test_dir_hit_only_scored_for_directional_cones`. **S / med**
- ~~**S13**~~ **DONE 2026-08-07** — `collect.is_stale` flags zero-range (high<=low) or zero/missing-volume bars;
  `collect.main` drops them at ingestion (becomes a gap, handled by gap-aware returns) and reports the count.
  Test `test_is_stale_detects_zero_range_and_volume`. (forming-last-bar exclusion left optional) **S-M / med**
- ~~**S14**~~ **[CERT] DONE 2026-08-07** — `forecast._lock` (fcntl.flock advisory, no-op off Unix) wraps `record`'s
  append and `score`'s read-modify-write in `main`, so concurrent hook jobs can't race and drop records
  (S7 dedupe also guards). Test `test_lock_context_manager_guards_ops`. **S / med**

### P3 — hygiene
- ~~**S15**~~ **DONE 2026-08-07** — `_confidence(p_target, ev)` ties confidence to the barrier hit-probability and a
  positive EV (not ad-hoc R^2/VR). Test `test_confidence_tiers_reflect_edge`. **S / low-med**
- ~~**S16**~~ **DONE 2026-08-07** — `barrier_hit_probabilities` returns `n`; `_ev_se` gives the multinomial MC
  standard error of EV; Gate C now requires `EV > se_ev` (clears zero by more than MC noise) and reports `EV±se`.
  Test `test_ev_standard_error_shrinks_with_paths`. **S / low-med**

### Still solid (do NOT touch)
No-lookahead fills; BH-FDR multiple testing; Wilson + Politis-Romano block + BCa CI machinery; `valid_ohlc` +
atomic store writes.

## Third-pass audit (2026-08-07, after the second-pass 16 items)
Fresh findings NOT in any DONE row above. Delegated adversarial re-derivation of the decision-critical numerics
(scipy venv), then source-confirmed each survivor. One NEW **HIGH** bug the first two passes missed — gold,
their test bed, has a near-24h session so its negligible gaps never surfaced it — plus three minor items. All
fixed, strict TDD. Commits `80bca3f` (T1+T2), `47daa1f` (T3+T4). Suite 77→79. The prior 36 findings re-verified
as genuinely resolved.

### P1 — correctness bug biasing the decision
- ~~**T1**~~ **[CERT] DONE 2026-08-07 (HIGH, risk-increasing)** — `variance_ratio` (`quant.py:336`) and
  `variance_ratio_test` (`quant.py:453-455`) measured the 1-bar variance denominator (and the test's `S`/mean)
  over the FULL return array while the k-sum numerator was already restricted to within-session segments (see
  S10). Cross-session gap returns therefore inflated `var1` and **DEFLATED VR on gapped instruments**
  (SPX/EURUSD/BTC). Verified on the venv: VR4 = 1.165 vs the correct within-session 2.384 (~0.49×). Two
  consequences via `decide.py:98,139` (raw returns WITH gaps + `times`): (1) Gate A momentum under-fires; (2)
  `vr_h`→`scale_sigma` understates horizon σ ~30% → **stop too tight + position too large** — silently
  reintroducing the #2 / S4 error, but only for gapped symbols (which is why gold slipped past two passes).
  Fix: compute `var1`, the demeaning, and `S` over within-segment returns only
  (`np.concatenate([r[s:e] for s,e in segs])`); the `times=None` path is byte-identical. Test
  `test_variance_ratio_denominator_is_within_session` (zeroing the excluded gap return must not move VR; RED
  showed 1.6e-05 vs 0.0044). **Directly extends S10** — S10 segmented the numerator but left the denominator
  whole. **S / high**

### P2 — consistency & decision logic
- ~~**T2**~~ **[CERT] DONE 2026-08-07** — `analyze.py:140` computed the displayed VR without `times`, so the VR
  the user READS differed from the VR `decide` ACTS on (and its filtered `ret` could stitch k-sums across a
  removed gap). Now routed through the same raw-returns+`times` segmented path decide gates on
  (`q.variance_ratio(q.log_returns(c), k, times=times)`), inheriting T1. **S / low**
- ~~**T3**~~ **[CERT] DONE 2026-08-07** — `_edge_precondition` (`decide.py:200`) validated the edge for the
  slope direction at bar `t`, but `decide` (`decide.py:99`) recomputes direction from `c[:t+1]`; on a slope flip
  a long-validated edge could authorize a SHORT trade in the walk-forward feedback. `_edge_precondition` now
  returns the validated direction (3-tuple); `decide` vetoes Gate B when it disagrees with the traded direction.
  Backward-compatible with 2-tuple overrides. Test `test_edge_override_direction_must_match_trade`. **Extends
  S1.** **S / low-med**

### P3 — hygiene
- ~~**T4**~~ **[CERT] DONE 2026-08-07** — `_confidence` (`decide.py:210`, introduced by S15) had a dead `'low'`
  branch: it is only called after Gate C guarantees `ev>0`, so the `not (ev>0)` guard never fired and only
  `high`/`medium` were ever emitted (the `Stance.confidence` "low | medium | high | none" contract was
  unsatisfiable for a trade). Now `_confidence(p_target, ev, se_ev)` grades by `margin = ev/se_ev` (Gate C
  already ensures `margin>1`): `margin<2 → low` (EV only marginally clears MC noise), else `high` if
  `p_target>=0.55` else `medium`. All three tiers reachable; `se_ev` was already in scope at the call site.
  Test `test_confidence_tiers_reflect_edge` updated (3-arg, asserts `low` reachable + zero-`se_ev` not-low).
  **Evolves S15.** **S / low**

### Live cross-asset validation (2026-08-07, 15m, 300 bars each, OANDA feed)
Screened gold + SPX500USD + EURUSD + USDJPY + GBPUSD + AUDUSD live over CDP after the fixes. **All six →
NO-TRADE**, every one vetoed at Gate A: all show **VR4 < 1 with negative z** (−0.5 to −2.0) — short-horizon
forex/index microstructure is mean-reverting, not momentum, so Gate A (wants `VR>1`) correctly refuses. Gold's
`analyze` reported "dropped 3 cross-gap returns" and its VR is now taken over the within-session denominator
(T1 operating in production; the effect is small on gold as predicted, material on SPX/forex). Crypto (BINANCE
feed) is not entitled on this account. Confirms the hardened engine's honest default across assets: flat is a
position.

### P2 — timeframe-scope miscalibration (surfaced by a higher-TF live screen)
- ~~**T5**~~ **[CERT] DONE 2026-08-07** — the gap-awareness (`_return_segments` + `log_returns(times=)`,
  `gap_tol=2×median_step`) was built for INTRADAY session gaps and misfired on **daily+** timeframes: a
  weekend is a ~3× step, so on gold DAILY (300 bars, +29.4%/14mo) **60/299 = 20% of legitimate daily returns
  were dropped**, `variance_ratio` fragmented into ~5-bar weekly segments (**VR8 → nan** at k=8), and the drift
  test lost power (n 299→239, t +0.92→+0.66). It did NOT flip a decision — gold daily is correctly NO-TRADE
  either way (the #1 guard: OLS-slope t=6.07 is the spurious I(1) statistic, the stationary drift t≈0.7–0.9 is
  honest and sub-significant) — but it nan'd the VR diagnostics and discarded real daily data. Fix: gate the
  gap-exclusion on an intraday cadence (`median step < _INTRADAY_STEP_MAX = 86400s`); daily+ series stay one
  segment / keep all returns. Verified on live gold daily: **VR8 nan → 0.88**, 0 returns dropped, verdict
  unchanged. Tests `test_log_returns_keeps_weekend_returns_on_daily`,
  `test_return_segments_not_fragmented_on_daily`, `test_variance_ratio_computable_on_daily_with_weekends`
  (intraday paths asserted unchanged). Commit `d59de86`. **S / med** *(surfaced by the 1h+D live screen)*

### Still solid (do NOT touch)
Everything on the first two passes' "do not touch" lists; the segmented numerator (S10) was correct — only its
denominator counterpart was missing (T1). The intraday gap heuristic itself is correct — T5 only bounded its
SCOPE to intraday cadences.

## Fourth-pass audit (2026-08-07, after the third-pass T1–T5)
Two independent adversarial auditors re-read the full toolkit against this ledger, hunting only NEW defects the
three prior passes missed. Both re-derived the decision-critical numerics rather than trusting the DONE rows.
Verdict: the machinery is genuinely solid — most re-checked items (T1 within-session VR denominator, barrier
first-passage MC, GARCH variance-targeting, BCa, PIT/pinball, leverage cap, walk-forward purge/embargo, `_ev_se`
covariance) held up. **Two risk-understating bugs found, plus three hygiene/honesty items. All fixed, TDD.**

### P1 — correctness bugs understating risk
- ~~**F1**~~ **[CERT] DONE 2026-08-07** — `max_drawdown` (`quant.py:416`) seeded the running peak from `eq[0]`
  (the FIRST trade's cumulative return), not from the starting equity. Any drawdown that begins before equity
  first rises above initial capital was invisible: `r=[-0.10,-0.05,+0.20]` reported **4.9%** vs the true
  **13.9%**, and `r=[-0.3]` reported **0.0%** on a trade that lost 26% — a wrong RISK number surfaced in the
  backtest (`BTStats.max_drawdown`), understating the metric several-fold. The #13 test only exercised a
  mid-series peak, so the from-start path was never tested. Fix: seed the equity path with the opening level
  (`eq = concatenate(([0.0], cumsum(r)))`) so initial capital is the first high-water mark. Test extends
  `test_max_drawdown_and_probabilistic_sharpe` (single-loss + from-start streak). Commit `5c3df59`. **S / HIGH**
- ~~**F2**~~ **[CERT] DONE 2026-08-07** — Gate C set its TARGET from a gap-CLEAN cone (`mc_block` over
  `log_returns(times=)`) but drew `p_target`/`p_stop` from `barrier_hit_probabilities`, which recomputed
  close-to-close returns over **all** bars with no session-gap filter (`quant.py:383`, no `times` arg). On a
  gap-prone trending instrument (SPX/index/stock/forex — the class T1/T5 flagged), overnight gaps aligned with
  the trend inflated the retained drift (`mu=rc.mean()`) and dispersion → `p_target` overstated, `p_stop`
  understated → EV and `_confidence` inflated in the risk-understating direction, with two DIFFERENT populations
  driving one R:R/EV decision. Gold's near-24h session masked it (their test bed). Fix: add a `times/gap_tol`
  path to `barrier_hit_probabilities` (shared `_gap_keep_mask` helper) that drops cross-session bars from the
  resample pool BEFORE the drift is measured, and pass `times` from Gate C; behaviour unchanged when `times`
  is None. Test `test_barrier_probabilities_drop_session_gaps` (altering an excluded gap bar must not move the
  probabilities under `times`; the gap-blind pool is contaminated by the same jump). **Completes the T1/T5
  gap-awareness sweep on the last decision-critical function it never reached.** Commit `68d9471`. **S / HIGH**

### P3 — hygiene & honesty
- ~~**F3**~~ **[CERT] DONE 2026-08-07** — the two degenerate early returns of `barrier_hit_probabilities`
  (`c.size<2 or horizon<1`, and `m==0`) omitted the `"n"` key that the happy path (S16) added, so downstream
  `_ev_se`/Gate C reading `bp["n"]` would `KeyError` on a 1-bar / `horizon<1` call instead of degrading. Latent
  (unreachable with 300-bar production arrays). Fix: add `"n": 0` to both. Commit `5c3df59` (bundled with F1).
  **S / low**
- ~~**F4**~~ **[CERT] DONE 2026-08-07** — `simulate_process` and `_edge_precondition` hardcoded `cost_bps=1.0`,
  so a non-default `Config.cost_bps` (e.g. gold-realistic 3.0) was honored by the live `decide` path (`bt.simulate(
  …, cfg.cost_bps, …)`) but SILENTLY IGNORED by the walk-forward feedback — the historical edge/expectancy were
  computed at the wrong cost. Not CLI-reachable (the CLI always builds `Config` with the 1.0 default), hence low.
  Fix: default `cost_bps=None` and resolve to `cfg.cost_bps` unless explicitly overridden. Test
  `test_simulate_process_honors_config_cost_bps` (two configs must diverge; higher cost never improves
  expectancy). Commit `1247c3a`. **S / low**
- ~~**F5**~~ **[CERT] DONE 2026-08-07** — the CLI `risk_cash` line read `risk $X at <price>`, which could be
  misread as a guaranteed worst-case loss even though the engine models slippage + gap-through fills everywhere
  else (S3). Relabeled to state it is the risk **at the stop level, excluding slippage/gap-through** — an
  honesty label, no behavioural change (widening the sizing denominator would be a deliberate quant change, out
  of scope for an audit). Commit `1247c3a`. **cosmetic / low**

### Still solid (do NOT touch)
Everything on the first three passes' "do not touch" lists, re-verified against source this pass: barrier
intrabar first-passage + both-barriers→stop conservatism, GARCH one-step reconstruction, BCa z0/acceleration,
`_independent_subset`/Wilson, backfill no-lookahead, `_ev_se` multinomial covariance sign, long/short stop &
target directions, walk-forward purge/embargo boundary, T1–T5. The displayed Gaussian forecast cone uses √h (not
VR-scaled) — this is intentional: the cone is calibration/display only, Gate C's decision uses the momentum-aware
`mc_block` + barriers, and the under-coverage was investigated exhaustively (no static fix; realized-coverage
reporting instead). No action.

## Gold-tail investigation (2026-08-08 — NO fix warranted, robust multi-asset evidence)
The prior calibration work claimed "the 90% under-coverage is gold-specific" from a small cross-symbol test.
This pass made it ROBUST: a one-command multi-asset backfill (`backfill.py --store analysis/data --symbols …`,
new `backfill_bars()` + tests) produced **400 non-overlapping, no-lookahead forecasts across 6 assets** (h=4/1h
on 15m). Gaussian cover90: **XAUUSD 0.82 (UNDER, CI [0.73,0.88] — 0.90 is outside, so real not noise)**; EURUSD
0.92, SPX500USD 0.90, USDJPY 0.93, GBPUSD 0.93, AUDUSD 0.92 (all OK). Pooled 0.89, dragged down only by gold.
Gold also has the worst-shaped cone (pinball 7.4 bps vs 1.2–2.9). All three cones fail equally on gold
(gaussian/bootstrap/student_t = 0.82/0.80/0.82), so it is NOT a tail-SHAPE problem — the whole band is too narrow.

Then an estimator sweep (analytic zero-drift band `z·σ·√h`, same windows) tested seven per-bar σ estimators for
gold's cover90 and their COST to the other five:
| candidate | XAU | EUR | SPX | JPY | GBP | AUD |
|---|---|---|---|---|---|---|
| base (GARCH, gap-filtered) | 0.83 | 0.92 | 0.90 | 0.93 | 0.93 | 0.92 |
| raw c2c (keeps gaps) | 0.86 | 0.92 | 0.92 | 0.88 | 0.98 | 0.93 |
| ewma raw / parkinson / GK | 0.85 | 0.92 | 0.90 | 0.88 | 0.98 | 0.92 |
| base ×1.15 | 0.87 | 0.93 | 0.97 | 0.97 | 0.95 | 0.93 |
| base ×1.30 | **0.93** | 0.95 | 0.98 | 0.97 | 0.97 | 0.95 |

**Conclusion: no static GLOBAL fix exists.** The only thing that lifts gold to 0.90 (×1.30) over-covers all five
already-calibrated assets (cover50 balloons to 0.71–0.80). Range estimators barely help gold (0.85) and push
GBPUSD to 0.98. Gold's gap is a genuine asset-specific fat-tail/jump property. Since the cone is display/calibration
ONLY (Gate C decides on `mc_block` + barriers, not this cone), the bounded cost does not justify a per-asset vol
multiplier — a tuning knob that would risk overfitting n=105. **Decision (user-approved 2026-08-08): document,
do NOT fix.** Rely on the realized-coverage reporting, which now carries robust multi-asset backfill evidence.
This EXTENDS the Task #3 "adaptive-vol — NO CHANGE warranted" finding to the tail specifically.

## Suggested sequencing
Quick wins first (all S-effort, each removes a real bias): **#6, #2, #4, #12, #15**. Then validity of the
whole pipeline: **#1, #3, #5**. Then P2 method upgrades. Every fix lands with a test (strict TDD).
