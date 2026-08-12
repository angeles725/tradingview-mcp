"""
Tests for the single-scalar, coverage-driven cone widener.

The conformal delta over-fits at these sample sizes (validated OOS, tvdecision
B20/B22). The scalar widener trades its per-band/per-side degrees of freedom for
ONE multiplicative factor k per symbol|tf: rescale the cone about its median so
the 90% band's REALIZED coverage climbs back toward nominal. Fewer knobs ->
harder to over-fit. These tests pin the shape and the fit/validate mechanics;
the parent runs the walk-forward honesty gate on real backfill separately.

Run with:
    <venv>/python analysis/test_coverage_scalar.py
"""
import cone_coverage as cc
import forecast as fc


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _cone(P5, P25, P50, P75, P95, model="gaussian"):
    return {"P5": P5, "P25": P25, "P50": P50, "P75": P75, "P95": P95,
            "p_up": 0.5, "model": model}


def _rec(P5, P95, realized, S0=100.0, P25=None, P75=None, P50=None,
         model="gaussian", made=0):
    """A minimal scored record carrying one model's cone and a realized close,
    with a symmetric cone about P50 by default."""
    P50 = P50 if P50 is not None else (P5 + P95) / 2
    P25 = P25 if P25 is not None else (P50 + P5) / 2
    P75 = P75 if P75 is not None else (P50 + P95) / 2
    return {
        "symbol": "X", "tf": "D", "horizon_bars": 5,
        "made_at_unix": made, "target_unix": made + 86400, "S0": S0,
        "cones": {model: {"P5": P5, "P25": P25, "P50": P50,
                          "P75": P75, "P95": P95, "p_up": 0.5, "model": model}},
        "realized": {"close": realized, "up": realized > S0, "models": {}},
    }


# --------------------------------------------------------------------------- #
# apply_coverage_scalar — the multiplicative rescale about the median
# --------------------------------------------------------------------------- #
def test_apply_scalar_k1_is_identity():
    cone = _cone(90.0, 96.0, 100.0, 104.0, 110.0)
    out = fc.apply_coverage_scalar(cone, 1.0)
    for k in ("P5", "P25", "P50", "P75", "P95"):
        _assert(abs(out[k] - cone[k]) < 1e-9, f"k=1 identity on {k}")
    _assert(out["p_up"] == 0.5, "p_up untouched")


def test_apply_scalar_widens_symmetrically_about_median():
    cone = _cone(90.0, 96.0, 100.0, 104.0, 110.0)
    out = fc.apply_coverage_scalar(cone, 2.0)
    # P50 fixed; each side's distance from P50 doubles.
    _assert(out["P50"] == 100.0, "median fixed")
    _assert(abs(out["P95"] - (100.0 + 2 * 10.0)) < 1e-9, "P95 -> P50 + 2*(P95-P50)")
    _assert(abs(out["P5"] - (100.0 - 2 * 10.0)) < 1e-9, "P5 -> P50 - 2*(P50-P5)")
    _assert(abs(out["P75"] - (100.0 + 2 * 4.0)) < 1e-9, "P75 -> P50 + 2*(P75-P50)")
    _assert(abs(out["P25"] - (100.0 - 2 * 4.0)) < 1e-9, "P25 -> P50 - 2*(P50-P25)")


def test_apply_scalar_stays_ordered():
    cone = _cone(90.0, 96.0, 100.0, 104.0, 110.0)
    out = fc.apply_coverage_scalar(cone, 1.7)
    _assert(out["P5"] <= out["P25"] <= out["P50"] <= out["P75"] <= out["P95"],
            "quantiles stay monotone")


# --------------------------------------------------------------------------- #
# coverage_scalar_fit — recover the scale a too-tight cone needs
# --------------------------------------------------------------------------- #
def test_fit_too_tight_returns_k_above_one():
    # Nominal 90% half-width = 10 (P5=90, P95=110 about P50=100), but realizations
    # actually spread ~2x that. A calibrated 90% band should then need k ~ 2.
    import math
    recs = []
    for i in range(60):
        # deterministic fan of |offsets| up to ~20 on alternating sides
        frac = (i + 1) / 60.0
        off = 20.0 * frac
        y = 100.0 + off if i % 2 == 0 else 100.0 - off
        recs.append(_rec(90.0, 110.0, y, made=i))
    k = fc.coverage_scalar_fit(recs, "gaussian", "90", min_n=20)
    _assert(k is not None, "enough records to fit")
    _assert(k > 1.4, f"too-tight cone needs widening, got k={k}")


def test_fit_calibrated_returns_k_near_one():
    # Realizations land right at the nominal band edge for the top decile ->
    # the 90%-quantile of the normalized residual is ~1 -> k ~ 1.
    recs = []
    for i in range(60):
        frac = (i + 1) / 60.0
        off = 10.0 * frac  # max |offset| = nominal half-width
        y = 100.0 + off if i % 2 == 0 else 100.0 - off
        recs.append(_rec(90.0, 110.0, y, made=i))
    k = fc.coverage_scalar_fit(recs, "gaussian", "90", min_n=20)
    _assert(k is not None, "enough records to fit")
    _assert(0.85 <= k <= 1.15, f"calibrated cone needs ~no widening, got k={k}")


def test_fit_below_min_n_returns_none():
    recs = [_rec(90.0, 110.0, 105.0, made=i) for i in range(10)]
    _assert(fc.coverage_scalar_fit(recs, "gaussian", "90", min_n=20) is None,
            "below min_n -> None")


def test_fit_is_clamped():
    # Absurdly too-tight: realizations 8x the band. k must clamp to <= 3.0.
    recs = [_rec(90.0, 110.0, 100.0 + (80.0 if i % 2 == 0 else -80.0), made=i)
            for i in range(40)]
    k = fc.coverage_scalar_fit(recs, "gaussian", "90", min_n=20)
    _assert(k is not None and k <= 3.0, f"k clamped to <=3, got {k}")


# --------------------------------------------------------------------------- #
# coverage_scalar_validate — walk-forward, OOS
# --------------------------------------------------------------------------- #
def test_validate_adj_beats_raw_on_too_tight():
    # A too-tight cone: raw test coverage well below 0.90, adjusted closer.
    recs = []
    for i in range(80):
        frac = ((i % 40) + 1) / 40.0
        off = 18.0 * frac
        y = 100.0 + off if i % 2 == 0 else 100.0 - off
        recs.append(_rec(90.0, 110.0, y, made=i))
    v = fc.coverage_scalar_validate(recs, "gaussian", "90", train_frac=0.7, min_n=20)
    _assert(v is not None, "validation ran")
    _assert(v["cover_raw_test"] < 0.90, f"raw is too-tight, got {v['cover_raw_test']}")
    _assert(abs(v["cover_adj_test"] - 0.90) <= abs(v["cover_raw_test"] - 0.90),
            f"adjusted coverage no worse than raw: {v}")
    _assert(v["k"] > 1.0, f"widened, k={v['k']}")


def test_validate_below_min_n_returns_none():
    recs = [_rec(90.0, 110.0, 105.0, made=i) for i in range(10)]
    _assert(fc.coverage_scalar_validate(recs, "gaussian", "90", min_n=20) is None,
            "below min_n -> None")


# --------------------------------------------------------------------------- #
# build_scalar_map — per symbol|tf, keyed on the reference model
# --------------------------------------------------------------------------- #
def test_build_scalar_map_groups_by_symbol_tf():
    recs = []
    for i in range(60):
        frac = (i + 1) / 60.0
        off = 20.0 * frac
        y = 100.0 + off if i % 2 == 0 else 100.0 - off
        recs.append(_rec(90.0, 110.0, y, made=i))
    m = cc.build_scalar_map(recs, min_n=20)
    _assert("X|D" in m, "grouped by symbol|tf")
    _assert(m["X|D"]["k"] > 1.0, "too-tight group gets k>1")
    _assert(m["X|D"]["n"] >= 20, "carries the scored count")


def test_build_scalar_map_omits_thin_groups():
    recs = [_rec(90.0, 110.0, 105.0, made=i) for i in range(5)]
    m = cc.build_scalar_map(recs, min_n=20)
    _assert("X|D" not in m, "thin group omitted")


def test_load_scalar_map_absent_is_empty():
    _assert(cc.load_scalar_map("/nonexistent/path/does-not-exist.json") == {},
            "absent map -> empty dict")


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run()
