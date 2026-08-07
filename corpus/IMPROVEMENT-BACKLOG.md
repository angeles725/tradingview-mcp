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

## Suggested sequencing
Quick wins first (all S-effort, each removes a real bias): **#6, #2, #4, #12, #15**. Then validity of the
whole pipeline: **#1, #3, #5**. Then P2 method upgrades. Every fix lands with a test (strict TDD).
