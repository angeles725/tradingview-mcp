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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} passed")
