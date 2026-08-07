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

## Suggested sequencing
Quick wins first (all S-effort, each removes a real bias): **#6, #2, #4, #12, #15**. Then validity of the
whole pipeline: **#1, #3, #5**. Then P2 method upgrades. Every fix lands with a test (strict TDD).
