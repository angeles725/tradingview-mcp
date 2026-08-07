"""
Tests for the forecast log + calibration scorer. Stdlib only. Run:
    python analysis/test_forecast.py
"""

import os
import tempfile

import forecast as fc


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _report():
    return {
        "symbol": "XAUUSD", "timeframe": "15", "horizon_bars": 4,
        "last_price": 100.0, "last_bar_unix": 1000, "bar_step_sec": 900,
        "cross_gap_dropped": 2,
        "monte_carlo": {
            "gaussian":  {"P5": 95, "P25": 98, "P50": 100, "P75": 102, "P95": 105,
                          "p_up": 0.50, "model": "gaussian"},
            "bootstrap": {"P5": 96, "P25": 99, "P50": 100, "P75": 101, "P95": 104,
                          "p_up": 0.48, "model": "bootstrap"},
            "student_t": {"P5": 90, "P25": 97, "P50": 100, "P75": 103, "P95": 110,
                          "p_up": 0.50, "model": "student_t(df=3.0)"},
        },
    }


def test_build_record_computes_target():
    rec = fc.build_record(_report())
    _assert(rec["target_unix"] == 1000 + 900 * 4, f"target wrong: {rec['target_unix']}")
    _assert(rec["S0"] == 100.0 and rec["realized"] is None, "record fields")
    _assert(set(rec["cones"]) == set(fc.MODELS), "all three cones captured")


def test_score_record_band_hits():
    rec = fc.build_record(_report())
    # realized 103: inside gaussian 90% [95,105] but OUTSIDE its 50% [98,102];
    # inside bootstrap 90% [96,104] and outside its 50% [99,101]; up vs S0.
    s = fc.score_record(rec, 103.0)
    _assert(s["realized"]["up"] is True, "103>100 is up")
    _assert(s["realized"]["models"]["gaussian"]["in_90"], "103 in gaussian 90%")
    _assert(not s["realized"]["models"]["gaussian"]["in_50"], "103 not in gaussian 50%")
    # realized 106: outside gaussian 90% [95,105], inside student_t 90% [90,110]
    s2 = fc.score_record(rec, 106.0)
    _assert(not s2["realized"]["models"]["gaussian"]["in_90"], "106 outside gaussian 90%")
    _assert(s2["realized"]["models"]["student_t"]["in_90"], "106 inside student_t 90%")


def test_dedupe_effective_n_and_wilson():
    # exact duplicates (same symbol/tf/made/horizon) must collapse
    r1 = fc.score_record(fc.build_record(_report()), 100.0)
    r1b = fc.score_record(fc.build_record(_report()), 101.0)
    cal = fc.calibration([r1, r1b])
    _assert(cal["n_scored"] == 1, f"exact duplicates must collapse, got {cal['n_scored']}")

    def mk(made, tgt):
        rec = fc.build_record(_report())
        rec["made_at_unix"] = made
        rec["target_unix"] = tgt
        return fc.score_record(rec, 100.0)

    recs = [mk(0, 100), mk(50, 150), mk(200, 300)]     # first two overlap, third separate
    cal2 = fc.calibration(recs)
    _assert(cal2["n_scored"] == 3 and cal2["n_eff"] == 2,
            f"effective n should be 2 non-overlapping, got {cal2['n_eff']}")
    _assert("cover_90_ci" in cal2["models"]["gaussian"], "must report a coverage CI")
    # Wilson interval sanity
    lo, hi = fc._wilson(5, 10)
    _assert(lo < 0.5 < hi and 0.0 <= lo and hi <= 1.0, "Wilson brackets 0.5 at 5/10")
    _assert((fc._wilson(5, 5)[1] - fc._wilson(5, 5)[0]) > (hi - lo) - 1.0, "n=5 CI is wide")


def test_pinball_bps_is_scale_invariant():
    # raw pinball is in PRICE units (BTC ~42 vs gold ~3 vs EURUSD ~0) -> not
    # comparable across symbols. pinball_bps normalizes by S0 so the SAME relative
    # move scores identically at any price level.
    s1 = fc.score_record(fc.build_record(_report()), 103.0)          # S0=100
    big = _report(); big["last_price"] = 10000.0
    for m in big["monte_carlo"].values():
        for k in ("P5", "P25", "P50", "P75", "P95"):
            m[k] *= 100.0
    s2 = fc.score_record(fc.build_record(big), 10300.0)              # S0=10000, same relative
    pb1 = s1["realized"]["models"]["gaussian"]["pinball_bps"]
    pb2 = s2["realized"]["models"]["gaussian"]["pinball_bps"]
    _assert(abs(pb1 - pb2) < 1e-6, f"pinball_bps must be scale-invariant: {pb1} vs {pb2}")
    _assert(pb1 > 0, "pinball_bps positive off the quantiles")


def test_pit_and_pinball_scoring_rules():
    lv = [0.05, 0.25, 0.5, 0.75, 0.95]
    vals = [90.0, 95.0, 100.0, 105.0, 110.0]
    # PIT: median -> 0.5, tails clamp, monotone in y
    _assert(abs(fc.pit(lv, vals, 100.0) - 0.5) < 1e-9, "median must map to PIT 0.5")
    _assert(fc.pit(lv, vals, 80.0) <= 0.05, "below P5 -> low PIT")
    _assert(fc.pit(lv, vals, 120.0) >= 0.95, "above P95 -> high PIT")
    _assert(fc.pit(lv, vals, 97.0) < fc.pit(lv, vals, 103.0), "PIT monotone in y")
    # pinball: strictly proper -> a far realized costs more than a near one
    _assert(fc.pinball_loss(lv, vals, 200.0) > fc.pinball_loss(lv, vals, 100.0),
            "worse forecast must have higher pinball loss")
    _assert(fc.pinball_loss(lv, vals, 100.0) > 0, "pinball positive off the quantiles")
    # calibration reports per-model mean pinball so cones can be RANKED
    rec = fc.build_record(_report())
    s1 = fc.score_record(rec, 100.0)
    s2 = fc.score_record(rec, 101.0)
    cal = fc.calibration([s1, s2])
    _assert("mean_pinball" in cal["models"]["gaussian"], "calibration must report mean_pinball")


def test_dir_hit_only_scored_for_directional_cones():
    # zero-drift cones sit at p_up ~ 0.5 -> no directional call (dir_hit None),
    # so dir_acc must not collapse to the base rate of up-moves.
    rec = fc.build_record(_report())          # p_up 0.50 / 0.48 / 0.50
    s = fc.score_record(rec, 105.0)
    for m in fc.MODELS:
        _assert(s["realized"]["models"][m]["dir_hit"] is None,
                f"{m}: a ~0.5 p_up must not be scored for direction")
    # a genuinely directional cone (p_up=0.7) IS scored — distinct made_at so the
    # two records are NOT deduped into one
    def mk_dir(made, y):
        r = fc.build_record(_report())
        r["cones"]["gaussian"]["p_up"] = 0.7
        r["made_at_unix"] = made; r["target_unix"] = made + 3600
        return fc.score_record(r, y)
    up = mk_dir(0, 105.0)         # up + bullish -> hit
    dn = mk_dir(4000, 95.0)       # down + bullish -> miss
    _assert(up["realized"]["models"]["gaussian"]["dir_hit"] is True, "up+bullish must hit")
    _assert(dn["realized"]["models"]["gaussian"]["dir_hit"] is False, "down+bullish must miss")
    cal = fc.calibration([up, dn, s])
    g = cal["models"]["gaussian"]
    _assert(g.get("dir_n") == 2, f"only directional records counted, got {g.get('dir_n')}")
    _assert(abs(g["dir_acc"] - 0.5) < 1e-9, f"1 hit / 2 dir records = 0.5, got {g.get('dir_acc')}")


def test_calibration_counts_coverage():
    def mk(made, y=None):
        rec = fc.build_record(_report())
        rec["made_at_unix"] = made; rec["target_unix"] = made + 3600
        return fc.score_record(rec, y) if y is not None else rec
    recs = [mk(0, 100.0),        # dead center: in all bands
            mk(4000, 103.0),     # in 90 for g/b, out of their 50
            mk(8000)]            # unscored (realized None)
    cal = fc.calibration(recs)
    _assert(cal["n_total"] == 3 and cal["n_scored"] == 2, "counts")
    g = cal["models"]["gaussian"]
    _assert(g["n"] == 2 and g["cover_90"] == 1.0, "both inside gaussian 90%")
    _assert(g["cover_50"] == 0.5, f"one of two inside gaussian 50%, got {g['cover_50']}")


def test_nearest_close_within_tolerance():
    bars = [{"time": 4500, "close": 10}, {"time": 4600, "close": 11},
            {"time": 5400, "close": 12}]
    _assert(fc.nearest_close(bars, 5400, 450) == 12, "exact match")
    _assert(fc.nearest_close(bars, 5410, 450) == 12, "within tolerance")
    _assert(fc.nearest_close(bars, 9999, 450) is None, "no bar within tolerance")


def test_coverage_table_groups_by_symbol_horizon():
    r1 = fc.score_record(fc.build_record(_report()), 100.0)          # XAUUSD|15|4
    r2 = fc.build_record(_report()); r2["symbol"] = "EURUSD"; r2["made_at_unix"] = 999
    r2 = fc.score_record(r2, 100.0)
    tbl = fc.coverage_table([r1, r2])
    _assert("XAUUSD|15|4" in tbl and "EURUSD|15|4" in tbl, "grouped by symbol|tf|horizon")
    g = tbl["XAUUSD|15|4"]["gaussian"]
    _assert("cover_90" in g and "cover_50" in g and g["n"] == 1, "per-group coverage")


def test_lock_context_manager_guards_ops():
    # score does a read-modify-write of the whole log; concurrent hook jobs must
    # not clobber it. _lock must be a usable context manager and ops under it work.
    path = os.path.join(tempfile.mkdtemp(), "forecasts.jsonl")
    rec = fc.build_record(_report())
    with fc._lock(path):
        fc.append_log(path, rec)
    _assert(len(fc.read_log(path)) == 1, "append under lock persisted")
    with fc._lock(path):
        fc.write_log(path, [])
    _assert(fc.read_log(path) == [], "rewrite under lock works")


def test_log_roundtrip(tmp=None):
    rec = fc.build_record(_report())
    path = os.path.join(tempfile.mkdtemp(), "forecasts.jsonl")
    fc.append_log(path, rec)
    fc.append_log(path, fc.score_record(rec, 101.0))
    back = fc.read_log(path)
    _assert(len(back) == 2, "two records round-trip")
    _assert(back[1]["realized"]["close"] == 101.0, "realized persisted")
    fc.write_log(path, back[:1])
    _assert(len(fc.read_log(path)) == 1, "rewrite truncates")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
