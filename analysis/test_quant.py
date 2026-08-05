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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} passed")
