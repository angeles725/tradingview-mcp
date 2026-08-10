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


def test_mc_block_wider_than_iid_under_momentum():
    # positively autocorrelated returns -> block cone must be WIDER than the i.i.d.
    # cone (persistence inflates horizon dispersion); this is the momentum-aware
    # distribution both Gate-C barriers now share.
    rng = np.random.default_rng(0)
    a = np.zeros(400)
    for i in range(1, 400):
        a[i] = 0.6 * a[i - 1] + rng.normal(0.0, 0.01)
    S0, hz = 100.0, 10
    iid = q.mc_bootstrap(S0, a, hz)
    blk = q.mc_block(S0, a, hz)
    _assert(blk["model"] == "block_bootstrap", "model tag must be block_bootstrap")
    _assert((blk["P95"] - blk["P5"]) > (iid["P95"] - iid["P5"]),
            f"block cone must be wider under momentum: {blk['P95'] - blk['P5']} vs {iid['P95'] - iid['P5']}")


def test_mc_block_drift_makes_cone_edge_aware():
    # drift_zero=False must carry the sample drift into the cone (used by Gate C so
    # the EV reflects the directional edge, not a zero-drift martingale).
    rng = np.random.default_rng(0)
    r = 0.002 + rng.normal(0.0, 0.001, 300)          # clear positive drift
    S0 = 100.0
    zero = q.mc_block(S0, r, 10, drift_zero=True)
    drift = q.mc_block(S0, r, 10, drift_zero=False)
    _assert(abs(zero["P50"] - S0) < S0 * 0.01, "zero-drift cone stays centered near S0")
    _assert(drift["P50"] > zero["P50"], "positive drift must shift the cone up")


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
    # First-passage MC over OHLC bars: which barrier is touched FIRST (intrabar).
    rng = np.random.default_rng(0)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.005, 500)))
    o = c.copy(); h = c * 1.001; l = c * 0.999      # small symmetric intrabar range
    entry = float(c[-1])
    bp = q.barrier_hit_probabilities(entry, o, h, l, c, 20,
                                     stop=entry * 0.98, target=entry * 1.02, direction=1)
    _assert(0 <= bp["p_target"] <= 1 and 0 <= bp["p_stop"] <= 1, "probs in range")
    _assert(abs(bp["p_target"] + bp["p_stop"] + bp["p_neither"] - 1.0) < 1e-9, "sum to 1")
    _assert(abs(bp["p_target"] - bp["p_stop"]) < 0.10,
            f"symmetric barriers should be ~equal, got {bp}")
    near = q.barrier_hit_probabilities(entry, o, h, l, c, 20, entry * 0.98, entry * 1.01, 1)
    far = q.barrier_hit_probabilities(entry, o, h, l, c, 20, entry * 0.98, entry * 1.04, 1)
    _assert(near["p_target"] > far["p_target"], "nearer target should hit more often")


def test_barrier_probabilities_drop_session_gaps():
    # Gate C reads the target off a gap-CLEAN cone but the barrier probabilities
    # must come from the SAME population — a cross-session gap return must not enter
    # the resample pool (else overnight jumps inflate p_target / understate p_stop).
    rng = np.random.default_rng(3)
    n_bars = 200
    c1 = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.004, n_bars)))
    # 5-min bars with one overnight session gap between index 100 and 101.
    step = 300.0
    times = np.arange(n_bars, dtype=float) * step
    times[101:] += 57600.0                     # 16h gap -> dt[100] >> gap_tol*step
    # c2 differs ONLY in the excluded cross-session return: scale the post-gap block
    # so rc[100] (the gap jump) changes but every within-session ratio is untouched.
    c2 = c1.copy(); c2[101:] *= 1.5
    o1, h1, l1 = c1.copy(), c1 * 1.001, c1 * 0.999
    o2, h2, l2 = c2.copy(), c2 * 1.001, c2 * 0.999
    entry, stop, target = 100.0, 98.0, 102.0
    p1 = q.barrier_hit_probabilities(entry, o1, h1, l1, c1, 20, stop, target, 1,
                                     drift_zero=False, times=times)
    p2 = q.barrier_hit_probabilities(entry, o2, h2, l2, c2, 20, stop, target, 1,
                                     drift_zero=False, times=times)
    _assert(p1["p_target"] == p2["p_target"] and p1["p_stop"] == p2["p_stop"],
            f"excluded gap bar must not move probabilities: {p1} vs {p2}")
    # Without `times` the gap return pollutes the pool and the probabilities DO move.
    d1 = q.barrier_hit_probabilities(entry, o1, h1, l1, c1, 20, stop, target, 1,
                                     drift_zero=False)
    d2 = q.barrier_hit_probabilities(entry, o2, h2, l2, c2, 20, stop, target, 1,
                                     drift_zero=False)
    _assert(abs(d1["p_target"] - d2["p_target"]) > 0.02,
            f"gap-blind pool should be contaminated by the jump: {d1} vs {d2}")


def test_barrier_uses_block_bootstrap():
    # The trade only exists because Gate A asserts VR>1 (momentum); barrier paths
    # must inherit that serial structure via the stationary block bootstrap, not
    # i.i.d. resampling (which erases the very dependence the strategy requires).
    orig = q.stationary_bootstrap_indices
    called = {"n": 0}
    try:
        def counting(*a, **k):
            called["n"] += 1
            return orig(*a, **k)
        q.stationary_bootstrap_indices = counting
        c = 100.0 * np.exp(np.cumsum(np.random.default_rng(0).normal(0.0, 0.005, 300)))
        q.barrier_hit_probabilities(float(c[-1]), c.copy(), c * 1.001, c * 0.999, c, 10,
                                    float(c[-1]) * 0.99, float(c[-1]) * 1.02, 1)
    finally:
        q.stationary_bootstrap_indices = orig
    _assert(called["n"] >= 1, "barrier MC must use the stationary block bootstrap")


def test_barrier_intrabar_raises_stop_probability():
    # Wider intrabar ranges must touch the stop MORE often than a close-only path;
    # zero-range bars must reduce to the close path.
    rng = np.random.default_rng(1)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.004, 400)))
    entry = float(c[-1]); stop = entry * 0.99; target = entry * 1.02
    zero = q.barrier_hit_probabilities(entry, c.copy(), c.copy(), c.copy(), c, 20,
                                       stop, target, 1)      # H=L=C -> close path
    wide = q.barrier_hit_probabilities(entry, c.copy(), c * 1.004, c * 0.996, c, 20,
                                       stop, target, 1)      # +/-0.4% intrabar
    _assert(wide["p_stop"] > zero["p_stop"],
            f"intrabar range must raise stop-hit prob: wide {wide['p_stop']} vs {zero['p_stop']}")


def test_max_drawdown_and_probabilistic_sharpe():
    # equity rises to +0.2 then a -0.3 return -> peak-to-trough dd = 1-exp(-0.3)
    r = np.array([0.1, 0.1, -0.3, 0.05])
    _assert(abs(q.max_drawdown(r) - (1 - math.exp(-0.3))) < 1e-9,
            f"max_drawdown wrong: {q.max_drawdown(r)}")
    _assert(q.max_drawdown(np.array([0.01, 0.02, 0.03])) == 0.0,
            "a monotonically rising equity has zero drawdown")
    # initial capital is the first high-water mark: a losing FIRST trade is a
    # real drawdown from the start, not zero (regression for the from-start bug).
    _assert(abs(q.max_drawdown(np.array([-0.3])) - (1 - math.exp(-0.3))) < 1e-9,
            f"a single losing trade must show its full drawdown: {q.max_drawdown(np.array([-0.3]))}")
    # a losing streak before equity ever rises above start: trough at -0.15
    dd_streak = q.max_drawdown(np.array([-0.10, -0.05, 0.20]))
    _assert(abs(dd_streak - (1 - math.exp(-0.15))) < 1e-9,
            f"from-start losing streak drawdown wrong: {dd_streak}")
    # PSR: a clear positive edge -> ~1; zero-mean noise -> ~0.5
    rng = np.random.default_rng(0)
    _assert(q.probabilistic_sharpe(rng.normal(0.02, 0.01, 200)) > 0.95,
            "clear positive edge should give PSR near 1")
    # EXACTLY zero sample mean -> observed Sharpe 0 -> PSR = 0.5 deterministically
    flat = np.array([0.01, -0.01] * 100)
    psr_flat = q.probabilistic_sharpe(flat)
    _assert(abs(psr_flat - 0.5) < 1e-9, f"zero-mean sample must give PSR 0.5, got {psr_flat:.3f}")


def test_variance_ratio_segments_across_gaps():
    # Gap-filtered returns become array-adjacent; VR's overlapping k-sums must NOT
    # stitch a pre-gap and a post-gap return together.
    r = np.array([0.01, -0.01, 0.01, -0.01, 0.02, -0.02, 0.02, -0.02])
    times = np.array([0, 60, 120, 180, 240, 100000, 100060, 100120, 100180])
    segs = q._return_segments(times, gap_tol=2.0)
    _assert(segs == [(0, 4), (5, 8)], f"segments must split at the gap, got {segs}")
    vr_seg = q.variance_ratio(r, 2, times=times)
    vr_all = q.variance_ratio(r, 2)
    _assert(not math.isnan(vr_seg), "segmented VR must be computable")
    _assert(vr_seg != vr_all, "segmentation must change VR vs the stitched version")
    # variance_ratio_test accepts times too (segmented) and returns finite z
    vr, z, p = q.variance_ratio_test(r, 2, times=times)
    _assert(not math.isnan(vr), "segmented VR test must be computable")


def test_variance_ratio_denominator_is_within_session():
    # The gap-boundary return (index 4 below) is excluded from the segmented
    # k-sum numerator; it MUST also be excluded from the 1-bar variance
    # denominator. Otherwise a large overnight/session gap inflates var1 and
    # DEFLATES VR on gapped instruments — understating horizon sigma, which
    # tightens the stop and oversizes the position (risk-increasing).
    r = np.array([0.01, -0.01, 0.012, -0.011, 0.5, 0.01, -0.01, 0.012])
    times = np.array([0, 60, 120, 180, 240, 100000, 100060, 100120, 100180])
    segs = q._return_segments(times, gap_tol=2.0)
    _assert(segs == [(0, 4), (5, 8)], f"expected gap split, got {segs}")
    # r[4] is the excluded gap return; its magnitude must not move VR.
    vr_big = q.variance_ratio(r, 2, times=times)
    r_small = r.copy()
    r_small[4] = 0.0
    vr_small = q.variance_ratio(r_small, 2, times=times)
    _assert(math.isclose(vr_big, vr_small, rel_tol=1e-12),
            f"excluded gap return must not affect segmented VR: {vr_big} vs {vr_small}")
    # the heteroskedasticity-robust VR test must be equally invariant.
    vr_bt, _, _ = q.variance_ratio_test(r, 2, times=times)
    vr_st, _, _ = q.variance_ratio_test(r_small, 2, times=times)
    _assert(math.isclose(vr_bt, vr_st, rel_tol=1e-12),
            f"excluded gap return must not affect VR test: {vr_bt} vs {vr_st}")


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


def _daily_times(steps_days):
    # Build unix-second daily timestamps from a list of day-steps (weekends = 3).
    day = 86400.0
    return np.concatenate([[0.0], np.cumsum(np.asarray(steps_days, float) * day)])


def test_log_returns_keeps_weekend_returns_on_daily():
    # On a DAILY cadence a weekend (Fri->Mon) is a normal bar boundary, not an
    # intraday session gap; the intraday gap-exclusion must NOT drop it, or ~20%
    # of legitimate daily returns vanish and drift/vol lose power.
    times = _daily_times([1, 1, 1, 1, 3] * 3)          # 3 weekends among weekdays
    c = 100.0 * np.exp(np.cumsum(np.full(times.size, 0.001)))
    r = q.log_returns(c, times=times)
    _assert(r.size == times.size - 1,
            f"daily weekend returns must be kept: got {r.size}, want {times.size - 1}")
    # intraday still drops its session gaps (unchanged behaviour)
    it = np.array([0, 60, 120, 100000, 100060], dtype=float)
    ci = np.array([100.0, 101.0, 102.0, 200.0, 202.0])
    _assert(q.log_returns(ci, times=it).size == 3, "intraday gap must still be dropped")


def test_return_segments_not_fragmented_on_daily():
    # Daily cadence must stay ONE segment — fragmenting per-week nans out VR at
    # higher k. Only intraday session gaps fragment.
    times = _daily_times([1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1])
    segs = q._return_segments(times)
    _assert(segs == [(0, times.size - 1)], f"daily must be one segment, got {segs}")


def test_variance_ratio_computable_on_daily_with_weekends():
    # The payoff: VR(8) must be COMPUTABLE on daily data with weekend gaps (was
    # nan because weekly ~4-5 bar segments never reached k=8).
    times = _daily_times(([1, 1, 1, 1, 3] * 9)[:-1])   # ~44 daily bars
    rng = np.random.default_rng(0)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, times.size)))
    vr8 = q.variance_ratio(q.log_returns(c), 8, times=times)
    _assert(not math.isnan(vr8), "VR(8) must be computable on daily data with weekend gaps")


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


# --------------------------------------------------------------------------- #
# HAR-RV over Yang-Zhang (research-backed volatility upgrade)
# --------------------------------------------------------------------------- #
def test_rogers_satchell_var_nonnegative_and_zero_on_flat():
    # Rogers-Satchell is a per-bar, drift-INDEPENDENT variance proxy; by
    # construction it is >= 0 and exactly 0 when the bar has no range.
    o = np.array([100.0, 101.0, 99.0])
    h = np.array([100.0, 103.0, 100.0])
    l = np.array([100.0, 100.0, 98.0])
    c = np.array([100.0, 102.0, 98.5])
    rs = q.rogers_satchell_var(o, h, l, c)
    _assert(rs.shape == (3,), "one RS variance per bar")
    _assert(np.all(rs >= -1e-15), "RS variance must be non-negative")
    _assert(rs[0] == 0.0, "flat bar (O=H=L=C) must give exactly 0 variance")
    _assert(rs[1] > 0.0, "a ranging bar must give positive variance")


def test_yang_zhang_vol_positive_and_flat_is_zero():
    o = np.array([100.0, 101.0, 100.5, 101.2, 100.8])
    h = np.array([101.0, 102.0, 101.5, 101.9, 101.3])
    l = np.array([99.5, 100.5, 100.0, 100.6, 100.1])
    c = np.array([100.8, 101.0, 101.1, 100.9, 101.0])
    yz = q.yang_zhang_vol(o, h, l, c)
    _assert(yz > 0.0, "Yang-Zhang sigma must be positive on a ranging series")
    _assert(math.isfinite(yz), "Yang-Zhang sigma must be finite")
    flat = np.full(5, 50.0)
    _assert(q.yang_zhang_vol(flat, flat, flat, flat) == 0.0,
            "a perfectly flat series has zero Yang-Zhang volatility")


def test_har_rv_forecast_recovers_constant_level():
    # On a constant realized-variance series the HAR forecast must return that
    # same level (no spurious drift), and never a negative variance.
    rv = np.full(80, 4e-6)
    pred = q.har_rv_forecast(rv, windows=(1, 5, 22))
    _assert(abs(pred - 4e-6) < 1e-9, f"constant RV must forecast itself, got {pred}")
    _assert(pred >= 0.0, "forecast variance must be non-negative")


def test_har_rv_forecast_short_series_falls_back_to_mean():
    rv = np.array([1e-6, 2e-6, 3e-6])   # shorter than the longest window
    pred = q.har_rv_forecast(rv, windows=(1, 5, 22))
    _assert(math.isfinite(pred) and pred > 0.0,
            "short series must fall back to a finite positive mean, not crash")
    _assert(abs(pred - float(np.mean(rv))) < 1e-12, "fallback must be the mean RV")


def test_blend_sigma_equal_weight_and_skips_none():
    _assert(abs(q.blend_sigma(0.02, 0.04) - 0.03) < 1e-12, "equal-weight mean")
    _assert(abs(q.blend_sigma(0.02, None) - 0.02) < 1e-12, "None operands are skipped")
    _assert(q.blend_sigma(None, None) is None, "all-None blend is None")


def test_cone_sigma_shared_recipe_blends_and_falls_back():
    # The single source of truth analyze.py and backfill.py share, so the cone
    # can't drift between live and backtest.
    rng = np.random.default_rng(3)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.004, 200)))
    o, h, l = c.copy(), c * 1.002, c * 0.998
    ret = q.log_returns(c)
    sig, v_har = q.cone_sigma(0.02, o, h, l, c, ret)
    _assert(v_har is not None and v_har > 0, "har sigma computed from OHLC")
    _assert(abs(sig - (0.02 + v_har) / 2) < 1e-12, "sigma is the 50/50 garch+har blend")
    # No GARCH and a flat OHLC (HAR undefined) -> falls back to EWMA of returns.
    flat = np.full(c.size, 100.0)
    sig2, v_har2 = q.cone_sigma(None, flat, flat, flat, flat, ret)
    _assert(v_har2 is None, "flat OHLC yields no HAR sigma")
    _assert(abs(sig2 - q.ewma_vol(ret)) < 1e-12, "fallback is EWMA when garch+har absent")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} passed")
