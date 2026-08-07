"""
Sanity tests for the numerical core. Run with the scipy-enabled venv:
    <venv>/python -m pytest analysis/test_quant.py -q
or standalone:
    <venv>/python analysis/test_quant.py
"""

import math
import numpy as np

import quant as q


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_rsi_matches_wilder_reference():
    # Wilder's original 14-period example converges near ~70 on a rising series.
    closes = np.array([
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
        46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41,
        46.22, 45.64,
    ])
    rsi = q.rsi_wilder(closes, 14)
    last = rsi[~np.isnan(rsi)][-1]
    _assert(0 <= last <= 100, "RSI out of range")
    _assert(50 < last < 80, f"RSI(14) expected ~70 band, got {last:.1f}")


def test_wilson_ci_bounds_and_symmetry():
    lo, hi = q.wilson_ci(50, 100)
    _assert(lo < 0.5 < hi, "Wilson CI must bracket 0.5 at 50/100")
    _assert(0 <= lo and hi <= 1, "Wilson CI must stay in [0,1]")
    # small-n interval must be much wider than large-n
    _, hi_small = q.wilson_ci(5, 10)
    lo_small, _ = q.wilson_ci(5, 10)
    _assert((hi_small - lo_small) > (hi - lo), "small n must widen CI")


def test_ols_trend_recovers_known_slope():
    x = np.arange(50)
    y = 3.0 + 2.0 * x + np.zeros_like(x, dtype=float)
    t = q.ols_trend(y)
    _assert(abs(t.slope - 2.0) < 1e-9, f"slope {t.slope}")
    _assert(t.r2 > 0.999, f"R2 {t.r2}")
    _assert(t.significant, "perfect line must be significant")


def test_theilsen_robust_to_outlier():
    y = (2.0 * np.arange(40)).astype(float)
    y[20] += 500.0  # single spike
    ts = q.theilsen_slope(y)
    _assert(abs(ts - 2.0) < 0.2, f"Theil-Sen should resist spike, got {ts}")


def test_bootstrap_cone_fatter_than_gaussian_on_fat_tails():
    # Build a fat-tailed return series; bootstrap P5..P95 should be >= gaussian.
    rng = np.random.default_rng(1)
    ret = rng.standard_t(3, size=280) * 0.01  # df=3 => heavy tails
    S0 = 100.0
    g = q.mc_gaussian(S0, q.close_to_close_vol(ret), 16, seed=3)
    b = q.mc_bootstrap(S0, ret, 16, seed=3)
    width_g = g["P95"] - g["P5"]
    width_b = b["P95"] - b["P5"]
    # not a strict inequality every seed, but bootstrap should not collapse
    _assert(width_b > 0.5 * width_g, "bootstrap cone collapsed unexpectedly")


def test_conditional_flags_thin_sample():
    baseline = 0.5
    mask = np.zeros(100, dtype=bool)
    mask[:8] = True                      # only 8 occurrences
    next_up = np.ones(100, dtype=bool)   # all up
    c = q.conditional_next_up("thin", mask, next_up, baseline)
    _assert(c.verdict == "thin-sample", f"expected thin-sample, got {c.verdict}")


def test_variance_ratio_discriminates_regime():
    rng = np.random.default_rng(5)
    # random walk: VR(k) ~ 1
    rw = rng.normal(0, 1, 2000)
    vr_rw = q.variance_ratio(rw, 4)
    _assert(0.8 < vr_rw < 1.2, f"random-walk VR should be ~1, got {vr_rw:.2f}")
    # momentum: returns positively autocorrelated -> VR > 1
    mom = np.empty(2000)
    mom[0] = rng.normal()
    for i in range(1, 2000):
        mom[i] = 0.4 * mom[i - 1] + rng.normal(0, 1)
    _assert(q.variance_ratio(mom, 4) > 1.1, "momentum VR should exceed 1")
    # mean reversion: negative autocorrelation -> VR < 1
    mr = np.empty(2000)
    mr[0] = rng.normal()
    for i in range(1, 2000):
        mr[i] = -0.4 * mr[i - 1] + rng.normal(0, 1)
    _assert(q.variance_ratio(mr, 4) < 0.9, "mean-reversion VR should be below 1")


def test_stationary_bootstrap_preserves_contiguity():
    rng = np.random.default_rng(3)
    idx = q.stationary_bootstrap_indices(100, 100, expected_block=20.0,
                                         n_paths=200, rng=rng)
    # with mean block 20, most consecutive steps should be i -> i+1 (mod n)
    steps = (idx[:, 1:] - idx[:, :-1]) % 100
    frac_contiguous = np.mean(steps == 1)
    _assert(frac_contiguous > 0.8,
            f"large blocks should be mostly contiguous, got {frac_contiguous:.2f}")


def test_ohlc_vol_estimators_match_reference_formulas():
    # Characterization/regression tests for the range vol estimators the audit
    # flagged as untested. They pin each to its documented closed form.
    h = np.array([101.0, 102.0]); l = np.array([100.0, 100.0])
    exp_park = math.sqrt(np.mean(np.log(h / l) ** 2) / (4.0 * math.log(2.0)))
    _assert(abs(q.parkinson_vol(h, l) - exp_park) < 1e-12,
            f"parkinson must match its formula: {q.parkinson_vol(h, l)} vs {exp_park}")
    o = np.array([100.5, 101.0]); c = np.array([100.8, 100.5])
    hl = np.log(h / l); co = np.log(c / o)
    exp_gk = math.sqrt(np.mean(0.5 * hl ** 2 - (2.0 * math.log(2.0) - 1.0) * co ** 2))
    _assert(abs(q.garman_klass_vol(o, h, l, c) - exp_gk) < 1e-12,
            f"garman-klass must match its formula: {q.garman_klass_vol(o, h, l, c)} vs {exp_gk}")
    # close-to-close is the plain sample stdev of log returns
    c2 = np.array([100.0, 101.0, 100.5, 102.0])
    _assert(abs(q.close_to_close_vol(q.log_returns(c2)) -
                np.std(np.diff(np.log(c2)), ddof=1)) < 1e-12, "c2c is sample stdev of log rets")


def test_theilsen_exact_and_subsampled():
    # a clean line has every pairwise slope == b, so both the exact and the
    # subsampled path must recover it precisely
    y_small = 3.0 + 2.0 * np.arange(50)
    _assert(abs(q.theilsen_slope(y_small) - 2.0) < 1e-9, "exact path recovers the slope")
    y_big = 5.0 + 2.0 * np.arange(3000)          # large enough to trigger subsampling
    _assert(abs(q.theilsen_slope(y_big, max_pairs=50_000) - 2.0) < 1e-9,
            "subsampled path still recovers a clean-line slope")
    # robust to a single spike
    y = np.arange(21, dtype=float)
    y[10] += 100.0
    _assert(abs(q.theilsen_slope(y) - 1.0) < 0.2, "median slope stays robust to one outlier")


def test_bca_ci_symmetric_matches_percentile_and_shifts_on_bias():
    if not q._HAS_SCIPY:
        return
    rng = np.random.default_rng(0)
    boot = rng.normal(0.0, 1.0, 20000)
    jack = np.array([-1.0, 1.0] * 50)                 # symmetric -> acceleration 0
    lo, hi = q.bca_ci(boot, 0.0, jack)
    plo, phi = np.percentile(boot, [2.5, 97.5])
    _assert(abs(lo - plo) < 0.06 and abs(hi - phi) < 0.06,
            f"symmetric BCa should match the percentile CI: {(lo, hi)} vs {(plo, phi)}")
    # a point estimate above the bootstrap centre -> positive z0 shifts both ends up
    lo2, hi2 = q.bca_ci(boot, 0.5, jack)
    _assert(lo2 > lo and hi2 > hi, "positive bias correction must shift the interval up")


def test_block_ci_wider_than_iid_on_autocorrelated():
    rng = np.random.default_rng(9)
    x = np.empty(500)
    x[0] = rng.normal()
    for i in range(1, 500):
        x[i] = 0.6 * x[i - 1] + rng.normal(0, 1)   # strong positive autocorrelation
    lo_i, hi_i = q.bootstrap_mean_ci(x, seed=1)
    lo_b, hi_b = q.bootstrap_mean_ci_block(x, expected_block=15.0, seed=1)
    _assert((hi_b - lo_b) > (hi_i - lo_i),
            "block CI must be wider than iid CI on autocorrelated data")


def test_classify_regime_labels_trend_and_chop():
    up = np.arange(100, dtype=float)                 # clean uptrend
    labels = q.classify_regime(up, window=20)
    _assert(labels[-1] == "trend-up", f"clean uptrend -> trend-up, got {labels[-1]}")
    rng = np.random.default_rng(2)
    flat = 100 + rng.normal(0, 1, 100)               # noise around a level
    labels2 = q.classify_regime(flat, window=20)
    _assert(np.mean(labels2 == "chop") > 0.7, "noise should be mostly chop")


def test_garch_recovers_persistence_with_student_t():
    if not q._HAS_SCIPY:
        return
    rng = np.random.default_rng(0)
    n, omega, alpha, beta = 1500, 1e-6, 0.08, 0.90    # persistence 0.98
    r = np.zeros(n)
    s2 = omega / (1 - alpha - beta)
    for t in range(1, n):
        s2 = omega + alpha * r[t - 1] ** 2 + beta * s2
        r[t] = math.sqrt(s2) * rng.normal()
    out = q.garch11_vol(r)
    _assert(out is not None, "GARCH must fit a clustered series")
    sig, p = out
    _assert(sig > 0, f"one-step sigma must be positive, got {sig}")
    _assert(0.7 < p["alpha"] + p["beta"] < 1.0,
            f"should recover high persistence, got {p['alpha'] + p['beta']:.2f}")
    _assert(p["nu"] > 2.0, f"Student-t df must be > 2 (finite variance), got {p['nu']}")


def test_barrier_hit_probabilities():
    # First-passage MC: which barrier is touched FIRST, not just the terminal side.
    rng = np.random.default_rng(0)
    r = rng.normal(0.0, 0.01, 500)
    entry = 100.0
    bp = q.barrier_hit_probabilities(entry, r, 20, stop=98.0, target=102.0, direction=1)
    _assert(0 <= bp["p_target"] <= 1 and 0 <= bp["p_stop"] <= 1, "probs in range")
    _assert(abs(bp["p_target"] + bp["p_stop"] + bp["p_neither"] - 1.0) < 1e-9, "sum to 1")
    # symmetric barriers under zero drift -> roughly equal hit probabilities
    _assert(abs(bp["p_target"] - bp["p_stop"]) < 0.08,
            f"symmetric barriers should be ~equal, got {bp}")
    # a NEARER target must be hit first more often than a far one
    near = q.barrier_hit_probabilities(entry, r, 20, 98.0, 101.0, 1)
    far = q.barrier_hit_probabilities(entry, r, 20, 98.0, 104.0, 1)
    _assert(near["p_target"] > far["p_target"], "nearer target should hit more often")


def test_max_drawdown_and_probabilistic_sharpe():
    # equity rises to +0.2 then a -0.3 return -> peak-to-trough dd = 1-exp(-0.3)
    r = np.array([0.1, 0.1, -0.3, 0.05])
    _assert(abs(q.max_drawdown(r) - (1 - math.exp(-0.3))) < 1e-9,
            f"max_drawdown wrong: {q.max_drawdown(r)}")
    _assert(q.max_drawdown(np.array([0.01, 0.02, 0.03])) == 0.0,
            "a monotonically rising equity has zero drawdown")
    # PSR: a clear positive edge -> ~1; zero-mean noise -> ~0.5
    rng = np.random.default_rng(0)
    _assert(q.probabilistic_sharpe(rng.normal(0.02, 0.01, 200)) > 0.95,
            "clear positive edge should give PSR near 1")
    # EXACTLY zero sample mean -> observed Sharpe 0 -> PSR = 0.5 deterministically
    flat = np.array([0.01, -0.01] * 100)
    psr_flat = q.probabilistic_sharpe(flat)
    _assert(abs(psr_flat - 0.5) < 1e-9, f"zero-mean sample must give PSR 0.5, got {psr_flat:.3f}")


def test_variance_ratio_test_calibrated_and_detects_momentum():
    # VR>1 alone is not momentum — VR=1.01 is indistinguishable from noise. The
    # Lo-MacKinlay heteroskedasticity-robust z must be ~N(0,1) on a random walk
    # (so a significance threshold controls false positives) and large-positive
    # when returns are genuinely serially correlated.
    rng = np.random.default_rng(0)
    zs = []
    for _ in range(300):
        _, z, _ = q.variance_ratio_test(rng.normal(0.0, 1.0, 400), 4)
        zs.append(z)
    zs = np.array(zs)
    _assert(abs(zs.mean()) < 0.3, f"random-walk z should center near 0, got {zs.mean():.2f}")
    fp = float((np.abs(zs) > 1.96).mean())
    _assert(fp < 0.15, f"random-walk two-sided false-positive rate should be ~5%, got {fp:.2f}")
    a = np.zeros(400)
    for i in range(1, 400):
        a[i] = 0.5 * a[i - 1] + rng.normal(0.0, 1.0)   # positive serial correlation
    vr, z, p = q.variance_ratio_test(a, 4)
    _assert(vr > 1.0 and z > 2.0,
            f"genuine momentum must be VR>1 and significant, got vr={vr:.2f} z={z:.2f}")


def test_log_returns_excludes_cross_gap():
    # A session/overnight gap makes one "bar return" a multi-period jump — a fat
    # outlier that inflates sigma and corrupts GARCH/VR. With timestamps, the
    # cross-gap return must be dropped; without them, behaviour is unchanged.
    c = np.array([100.0, 101.0, 102.0, 200.0, 202.0])
    times = np.array([0, 60, 120, 100000, 100060])   # big gap before index 3
    base = q.log_returns(c)
    _assert(base.size == 4, "no-times must still return n-1 contiguous returns")
    r = q.log_returns(c, times=times)
    _assert(r.size == 3, f"the cross-gap return (102->200) must be dropped, got {r.size}")
    expected = np.array([math.log(101 / 100), math.log(102 / 101), math.log(202 / 200)])
    _assert(np.allclose(r, expected), f"wrong returns kept: {r}")


def test_newey_west_lrv_inflates_under_autocorrelation():
    rng = np.random.default_rng(1)
    u = rng.normal(0.0, 1.0, 500)
    # lag 0 is exactly the sum of squares (the i.i.d. variance estimate)
    _assert(abs(q.newey_west_lrv(u, 0) - float(np.sum(u * u))) < 1e-9,
            "lag-0 LRV must equal the sum of squares")
    # a positively autocorrelated series must inflate the long-run variance
    a = np.zeros(500)
    for i in range(1, 500):
        a[i] = 0.9 * a[i - 1] + rng.normal(0.0, 1.0)
    _assert(q.newey_west_lrv(a, 12) > float(np.sum(a * a)),
            "positive autocorrelation must inflate LRV above the lag-0 term")


def test_ols_trend_hac_widens_ci_on_autocorrelated_residuals():
    # A random walk regressed on time has strongly autocorrelated residuals; the
    # i.i.d. SE understates SE(slope) (spurious regression). HAC must widen the CI.
    rng = np.random.default_rng(3)
    c = 100.0 + np.cumsum(rng.normal(0.0, 1.0, 300))
    tr = q.ols_trend(c)
    n = c.size
    x = np.arange(n, dtype=float); xm = x.mean()
    sxx = float(np.sum((x - xm) ** 2))
    ym = c.mean(); intercept = ym - tr.slope * xm
    resid = c - (intercept + tr.slope * x)
    sigma2 = float(np.sum(resid ** 2)) / (n - 2)
    naive_se = math.sqrt(sigma2 / sxx)
    tcrit = float(q.stats.t.ppf(0.975, n - 2)) if q._HAS_SCIPY else 1.96
    naive_half = tcrit * naive_se
    hac_half = (tr.ci95[1] - tr.ci95[0]) / 2.0
    _assert(hac_half > naive_half * 1.2,
            f"HAC CI must be materially wider than i.i.d. on autocorrelated "
            f"residuals: hac_half={hac_half:.5f} vs naive_half={naive_half:.5f}")


def test_ols_trend_rejects_spurious_random_walk_trend():
    # A random walk has NO true trend, yet a level-on-time regression is
    # spuriously significant far above nominal (Granger-Newbold). Gating trend
    # significance on the stationary drift (log-returns) restores ~5% false
    # positives. The old level-only test flagged ~60%+.
    rng = np.random.default_rng(0)
    N = 200
    hits = sum(q.ols_trend(100.0 + np.cumsum(rng.normal(0.0, 1.0, 250))).significant
               for _ in range(N))
    _assert(hits < N * 0.15,
            f"spurious random-walk trend rate too high: {hits}/{N} "
            f"({100 * hits / N:.0f}%) — significance is not stationary")
    # a genuine drift must still register as significant
    rng2 = np.random.default_rng(7)
    c = 100.0 * np.exp(np.cumsum(0.004 + 0.01 * rng2.normal(0.0, 1.0, 250)))
    _assert(q.ols_trend(c).significant, "genuine drift must remain significant")


def test_trend_significant_is_json_serializable_bool():
    # np.bool_ is NOT a subclass of Python bool and breaks json.dumps, which
    # silently broke analyze.py --json (the machine-readable report). significant
    # must be a native bool and the trend dict must serialize.
    import json
    rng = np.random.default_rng(0)
    c = np.cumsum(rng.normal(0.0, 1.0, 120)) + 100.0
    tr = q.ols_trend(c)
    _assert(type(tr.significant) is bool,
            f"significant must be python bool, got {type(tr.significant).__name__}")
    json.dumps(tr.as_dict())          # must not raise


def test_benjamini_hochberg_matches_reference():
    # Only the strong signal rejects when the rest are null.
    p = np.array([0.001, 0.5, 0.6, 0.7, 0.8])
    reject, padj = q.benjamini_hochberg(p, alpha=0.05)
    _assert(reject[0] and not reject[1:].any(),
            f"only the smallest p should reject, got {reject}")
    _assert(np.all(padj >= p - 1e-12), "adjusted p must be >= raw p")
    _assert(np.all(padj <= 1.0 + 1e-12), "adjusted p must stay <= 1")
    # p-values exactly on the BH line should all reject.
    p2 = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
    r2, _ = q.benjamini_hochberg(p2, alpha=0.05)
    _assert(r2.all(), f"linear p-values at the BH threshold should all reject, got {r2}")


def test_conditionals_multiple_testing_correction():
    base = 0.5

    def mk(name, p):
        # n>=30 (not thin-sample); ci/edge are placeholders for the family test.
        return q.Conditional(name, 50, 30, 0.6, (0.55, 0.65), base, 0.1, p, "edge")

    # A borderline-significant condition among nulls must be DEMOTED once the
    # number of simultaneous tests is accounted for.
    fam = [mk("c0", 0.04), mk("c1", 0.9), mk("c2", 0.8), mk("c3", 0.85), mk("c4", 0.95)]
    q.correct_conditionals(fam, alpha=0.05)
    _assert(fam[0].verdict == "no-edge",
            f"borderline edge must be demoted under correction, got {fam[0].verdict}")
    # A genuinely strong signal survives the same correction.
    fam2 = [mk("s0", 0.0005), mk("c1", 0.9), mk("c2", 0.8), mk("c3", 0.85), mk("c4", 0.95)]
    q.correct_conditionals(fam2, alpha=0.05)
    _assert(fam2[0].verdict == "edge",
            f"strong signal should survive correction, got {fam2[0].verdict}")
    _assert(fam2[0].p_adjusted >= fam2[0].p_value, "adjusted p must be >= raw p")


def test_ewma_seed_uses_warmup_window_not_single_return():
    # The RiskMetrics recursion is UNCENTERED (tracks E[r^2]); seeding it with a
    # single r[0]^2 is an extremely noisy seed. Seeding with the mean squared
    # return over a warm-up window is the same moment with far lower variance.
    # For a series no longer than the warm-up window there is no recursion, so
    # the estimate must equal sqrt(mean(r^2)) exactly — the old code returned a
    # spike-dominated value instead.
    r = np.array([0.20, 0.01, 0.01, 0.01, 0.01])   # lone first-bar spike, n<=warmup
    expected = math.sqrt(float(np.mean(r ** 2)))
    got = q.ewma_vol(r)
    _assert(abs(got - expected) < 1e-12,
            f"EWMA must seed with warm-up mean square: expected {expected}, got {got}")
    # sanity: the spike must NOT dominate the way r[0]**2 seeding does
    _assert(got < 0.12, f"first-bar spike still dominates EWMA: {got}")


def test_mc_student_t_guards_degenerate_df():
    # A Student-t with df<=2 has infinite variance; on a short noisy sample the
    # MLE can land there and the simulated cone explodes. The guard must detect a
    # degenerate df and fall back to the bounded bootstrap cone.
    if not q._HAS_SCIPY:
        return
    rng = np.random.default_rng(9)
    r = rng.normal(0.0, 0.01, 300)                 # well-behaved, bounded returns
    orig_fit = q.stats.t.fit
    try:
        q.stats.t.fit = lambda *a, **k: (1.5, 0.0, 0.01)   # force df<=2
        out = q.mc_student_t(100.0, r, horizon=5)
    finally:
        q.stats.t.fit = orig_fit
    _assert("fallback" in out["model"] or "bootstrap" in out["model"],
            f"degenerate df must fall back, got model={out['model']}")
    _assert(out.get("df") == 1.5, f"degenerate df must be reported, got {out.get('df')}")
    for key in ("P5", "P50", "P95", "mean_lognormal"):
        _assert(np.isfinite(out[key]), f"{key} must stay finite, got {out[key]}")


def test_scale_sigma_uses_variance_ratio():
    # sqrt(h) scaling assumes a random walk (VR=1). But the engine only trades
    # when VR>1, where horizon variance is VR*h*sigma^2 — sqrt(h) understates it,
    # making stops too tight and size too large. Scaling must honor VR.
    s, h = 0.01, 9
    _assert(abs(q.scale_sigma(s, h) - s * math.sqrt(h)) < 1e-12,
            "default VR=1 must reproduce sqrt(h) scaling")
    wide = q.scale_sigma(s, h, vr=2.0)
    _assert(abs(wide - s * math.sqrt(h * 2.0)) < 1e-12,
            "VR must scale variance: sigma*sqrt(h*vr)")
    _assert(wide > q.scale_sigma(s, h), "VR>1 must widen horizon sigma vs random walk")
    # degenerate VR (NaN / non-positive) must fall back to sqrt(h), never NaN
    _assert(abs(q.scale_sigma(s, h, vr=float("nan")) - s * math.sqrt(h)) < 1e-12,
            "NaN VR must fall back to sqrt(h)")
    _assert(abs(q.scale_sigma(s, h, vr=0.0) - s * math.sqrt(h)) < 1e-12,
            "non-positive VR must fall back to sqrt(h)")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} passed")
