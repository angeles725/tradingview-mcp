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


def test_score_pending_from_store_is_symbol_correct():
    # A matured forecast that fell off the live window must score against ITS OWN
    # symbol's persistent store — never another symbol's bars at the same time.
    import collect
    gold = _report(); gold["symbol"] = "OANDA:XAUUSD"
    eur = _report();  eur["symbol"] = "OANDA:EURUSD"
    recs = [fc.build_record(gold), fc.build_record(eur)]
    target = recs[0]["target_unix"]                       # same maturity time
    with tempfile.TemporaryDirectory() as d:
        # two stores, DIFFERENT close at the target time
        for sym, close in (("OANDA:XAUUSD", 103.0), ("OANDA:EURUSD", 97.0)):
            path = collect.store_path(d, sym, "15")
            bars = [{"time": target, "open": close, "high": close, "low": close,
                     "close": close, "volume": 1}]
            collect.save_store(path, bars)
        out, n = fc.score_pending(recs, store_dir=d)
        _assert(n == 2, f"both matured records should score, got {n}")
        g = out[0]["realized"]; e = out[1]["realized"]
        _assert(g is not None and abs(g["close"] - 103.0) < 1e-9,
                f"gold scored against gold store: {g}")
        _assert(e is not None and abs(e["close"] - 97.0) < 1e-9,
                f"eur scored against eur store (NOT gold's 103): {e}")


def test_score_pending_symbol_filter_prevents_cross_scoring():
    # With a single-symbol bars window, only matching-symbol records may score.
    gold = _report(); gold["symbol"] = "OANDA:XAUUSD"
    eur = _report();  eur["symbol"] = "OANDA:EURUSD"
    recs = [fc.build_record(gold), fc.build_record(eur)]
    target = recs[0]["target_unix"]
    bars = [{"time": target, "open": 103.0, "high": 103.0, "low": 103.0,
             "close": 103.0, "volume": 1}]
    out, n = fc.score_pending(recs, bars=bars, symbol="OANDA:XAUUSD")
    _assert(n == 1, f"only the gold record should score, got {n}")
    _assert(out[0]["realized"] is not None, "gold scored")
    _assert(out[1]["realized"] is None, "eur must NOT be scored against gold bars")


def test_score_pending_rejects_absurd_cross_symbol_jump():
    # Defense-in-depth beyond the symbol filter: nearest_close matches on TIME
    # only, so a mis-filtered multi-symbol window can hand a record another
    # symbol's price (e.g. GBPUSD ~1.35 scored against USDJPY ~159). A move that
    # large over these horizons is impossible -> refuse to score, stay pending.
    r = _report(); r["symbol"] = "OANDA:GBPUSD"; r["last_price"] = 1.35
    for c in r["monte_carlo"].values():
        for k in ("P5", "P25", "P50", "P75", "P95"):
            c[k] = 1.35
    rec = fc.build_record(r)
    target = rec["target_unix"]
    poison = [{"time": target, "open": 159.0, "high": 159.0, "low": 159.0,
               "close": 159.0, "volume": 1}]
    out, n = fc.score_pending([rec], bars=poison)
    _assert(n == 0, f"absurd jump must not score, got {n}")
    _assert(out[0]["realized"] is None, "record must stay pending after poison price")
    # a sane close at the same time still scores normally
    sane = [{"time": target, "open": 1.351, "high": 1.351, "low": 1.351,
             "close": 1.351, "volume": 1}]
    out2, n2 = fc.score_pending([fc.build_record(r)], bars=sane)
    _assert(n2 == 1 and out2[0]["realized"] is not None, "sane close should score")


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


def test_calibration_reports_independent_cover_50_ci():
    # #21: the pooled cover_50 over overlapping forecasts overstates the evidence
    # (a quiet regime keeps price inside P25-P75). cover_50_ci must be computed over
    # the INDEPENDENT subset, exactly like cover_90_ci, so it cannot be inflated.
    def mk(made, tgt, y):
        rec = fc.build_record(_report())
        rec["made_at_unix"] = made
        rec["target_unix"] = tgt
        return fc.score_record(rec, y)
    # first two windows overlap (1 independent), third is separate -> n_eff = 2
    recs = [mk(0, 100, 100.0), mk(50, 150, 100.0), mk(200, 300, 100.0)]
    cal = fc.calibration(recs)
    g = cal["models"]["gaussian"]
    _assert("cover_50_ci" in g, "must report a 50% coverage CI")
    lo, hi = g["cover_50_ci"]
    _assert(0.0 <= lo <= hi <= 1.0, "valid Wilson interval")
    # it must equal the Wilson interval over the INDEPENDENT subset, not the pool
    indep = fc._independent_subset([r for r in fc._dedupe(recs) if r.get("realized")])
    k = sum(r["realized"]["models"]["gaussian"]["in_50"] for r in indep)
    exp = fc._wilson(k, len(indep))
    _assert(abs(lo - exp[0]) < 1e-9 and abs(hi - exp[1]) < 1e-9,
            f"cover_50_ci must be over the independent subset: {(lo, hi)} vs {exp}")
    _assert(g.get("n_eff") == len(indep), "must expose the independent count per model")


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


# --------------------------------------------------------------------------- #
# Conformal calibration layer (research-backed coverage guarantee)
# --------------------------------------------------------------------------- #
def _scored(P5, P95, realized, S0=100.0, P25=None, P75=None, model="gaussian", made=0):
    """A minimal scored record carrying one model's cone and a realized close.
    `made` makes the dedupe key unique (symbol/tf/made_at/horizon)."""
    P25 = P25 if P25 is not None else (P5 + P95) / 2 - 1
    P75 = P75 if P75 is not None else (P5 + P95) / 2 + 1
    return {
        "symbol": "X", "tf": "15", "horizon_bars": 4,
        "made_at_unix": made, "target_unix": made + 3600, "S0": S0,
        "cones": {model: {"P5": P5, "P25": P25, "P50": (P5 + P95) / 2,
                          "P75": P75, "P95": P95, "p_up": 0.5, "model": model}},
        "realized": {"close": realized, "up": realized > S0, "models": {}},
    }


def test_dedupe_prefers_scored_over_unscored():
    # Same forecast key recorded twice: once SCORED, once not. Dedupe must keep the
    # scored copy regardless of order (else calibration silently loses outcomes).
    base = dict(symbol="X", tf="15", made_at_unix=10, horizon_bars=4)
    scored = {**base, "realized": {"close": 1.0}}
    unscored = {**base, "realized": None}
    for order in ([scored, unscored], [unscored, scored]):
        out = fc._dedupe(order)
        _assert(len(out) == 1, "one record per key")
        _assert(out[0]["realized"] is not None, "the scored copy must survive dedupe")


def test_dedupe_collapses_same_hourly_target_keeps_freshest():
    # Overlapping hook ticks record the SAME (symbol, tf, horizon, target_unix)
    # more than once with different made_at. They must collapse to one, keeping the
    # freshest forecast — so a target hour is never double-counted in calibration.
    def mk(made, s0):
        rec = fc.build_record(_report())
        rec["made_at_unix"] = made
        rec["target_unix"] = 5000          # same target hour for both
        rec["S0"] = s0
        return rec
    out = fc._dedupe([mk(100, 100.0), mk(200, 101.0)])
    _assert(len(out) == 1, f"same-target forecasts must collapse, got {len(out)}")
    _assert(out[0]["made_at_unix"] == 200, "the freshest (latest made_at) must survive")
    # a SCORED copy still beats a fresher UNSCORED one (never lose an outcome)
    scored_old = fc.score_record(mk(100, 100.0), 100.0)
    unscored_new = mk(300, 100.0)
    out2 = fc._dedupe([unscored_new, scored_old])
    _assert(len(out2) == 1 and out2[0]["realized"] is not None,
            "a scored record must survive over a fresher unscored twin")
    # distinct targets are independent forecasts -> both survive
    a = mk(100, 100.0); b = mk(100, 100.0); b["target_unix"] = 9000
    _assert(len(fc._dedupe([a, b])) == 2, "distinct targets must NOT collapse")


def test_aci_adapted_level_widens_after_misses_tightens_after_hits():
    # ACI online: a run of raw-band MISSES must raise the adapted coverage level
    # above nominal (widen the next band); a run of HITS must lower it (tighten).
    def mk(made, y):
        rec = fc.build_record(_report())
        rec["made_at_unix"] = made
        rec["target_unix"] = made + 3600      # distinct targets -> all survive
        return fc.score_record(rec, y)
    misses = [mk(i * 4000, 130.0) for i in range(12)]   # 130 > P95=105 -> raw miss
    hits = [mk(i * 4000, 100.0) for i in range(12)]      # 100 = median -> raw hit
    lvl_miss = fc.aci_adapted_level(misses, "gaussian", "90")
    lvl_hit = fc.aci_adapted_level(hits, "gaussian", "90")
    _assert(lvl_miss > 0.90, f"misses must widen the level above nominal: {lvl_miss}")
    _assert(lvl_hit < 0.90, f"hits must tighten the level below nominal: {lvl_hit}")


def test_conformalize_band_adaptive_reports_aci_level_and_widens_on_misses():
    def mk(made, y):
        rec = fc.build_record(_report())
        rec["made_at_unix"] = made
        rec["target_unix"] = made + 3600
        return fc.score_record(rec, y)
    recs = [mk(i * 4000, 130.0) for i in range(12)]      # persistent misses
    static = fc.conformalize_band(recs, "gaussian", "90")
    adaptive = fc.conformalize_band(recs, "gaussian", "90", adaptive=True)
    _assert("aci_level" not in static, "static mode must not emit aci_level")
    _assert(adaptive.get("aci_level", 0) > 0.90, "adaptive level rises on persistent misses")
    _assert(adaptive["delta_frac"] >= static["delta_frac"],
            "adaptive band must widen at least as much as static on misses")
    _assert("static_delta_frac" in adaptive, "adaptive must expose the static delta for reference")


def test_s0_contaminated_flags_cross_symbol_price():
    # RECORD-side contamination guard: a feed-not-ready symbol switch can hand the
    # record another symbol's price. Compared to the symbol's own store median, a
    # cross-symbol S0 is wildly off and must be flagged; a normal S0 must pass.
    import collect
    d = tempfile.mkdtemp()
    rows = [{"time": 1000 + i * 900, "open": 1.15, "high": 1.151, "low": 1.149,
             "close": 1.15, "volume": 10} for i in range(30)]
    collect.save_store(collect.store_path(d, "OANDA:EURUSD", "15"), rows)
    _assert(fc.s0_contaminated("OANDA:EURUSD", "15", 7757.0, d) is True,
            "an SPX-level price recorded for EURUSD must be flagged")
    _assert(fc.s0_contaminated("OANDA:EURUSD", "15", 1.152, d) is False,
            "a normal EURUSD S0 must pass")
    _assert(fc.s0_contaminated("OANDA:EURUSD", "15", 1.15, "/nonexistent") is False,
            "no store reference -> cannot judge -> not flagged")


def test_crps_from_quantiles_properties():
    lv = fc.QUANTILE_LEVELS
    narrow = [98.0, 99.0, 100.0, 101.0, 102.0]
    wide = [90.0, 95.0, 100.0, 105.0, 110.0]
    # non-negative, and symmetric around the median for a symmetric cone
    _assert(fc.crps_from_quantiles(lv, narrow, 100.0) >= 0, "CRPS non-negative")
    a = fc.crps_from_quantiles(lv, narrow, 100.0 + 1.5)
    b = fc.crps_from_quantiles(lv, narrow, 100.0 - 1.5)
    _assert(abs(a - b) < 1e-9, "CRPS symmetric for a symmetric cone")
    # sharpness: at the median, a narrower cone scores BETTER (lower) than a wide one
    _assert(fc.crps_from_quantiles(lv, narrow, 100.0) < fc.crps_from_quantiles(lv, wide, 100.0),
            "a sharper cone must have lower CRPS when the realized is at the median")
    # a realized far in the tail costs more than one at the median
    _assert(fc.crps_from_quantiles(lv, narrow, 100.0) < fc.crps_from_quantiles(lv, narrow, 110.0),
            "a tail outcome must cost more than a central one")


def test_score_record_reports_crps():
    rec = fc.build_record(_report())
    s = fc.score_record(rec, 103.0)
    g = s["realized"]["models"]["gaussian"]
    _assert("crps" in g and g["crps"] >= 0, "score_record attaches a CRPS per model")
    _assert("crps_bps" in g and g["crps_bps"] >= 0, "CRPS also normalized to bps of S0")


def test_trade_levels_from_cone_long_and_short():
    cone = {"P5": 95.0, "P25": 98.0, "P50": 100.0, "P75": 102.0, "P95": 108.0}
    lo = fc.trade_levels(cone, "long")
    _assert(lo["entry"] == 100.0 and lo["stop_loss"] == 95.0 and lo["take_profit"] == 108.0,
            "long: SL=P5, TP=P95, entry=P50")
    _assert(abs(lo["risk"] - 5.0) < 1e-9 and abs(lo["reward"] - 8.0) < 1e-9, "risk/reward distances")
    _assert(abs(lo["rr"] - 1.6) < 1e-9, "R:R = reward/risk")
    _assert(abs(lo["sl_pct"] - 5.0) < 1e-9 and abs(lo["tp_pct"] - 8.0) < 1e-9, "distances in %")
    sh = fc.trade_levels(cone, "short")
    _assert(sh["stop_loss"] == 108.0 and sh["take_profit"] == 95.0, "short: SL=P95, TP=P5")
    _assert(abs(sh["rr"] - 0.625) < 1e-9, "short R:R")


def test_size_for_risk_from_levels():
    lv = fc.trade_levels({"P5": 95.0, "P50": 100.0, "P95": 108.0}, "long")
    s = fc.size_for_risk(lv, equity=10000.0, risk_pct=1.0)
    _assert(abs(s["risk_cash"] - 100.0) < 1e-9, "1% of 10k = 100 cash at risk")
    _assert(abs(s["units"] - 20.0) < 1e-9, "units = risk_cash / risk_per_unit (100/5)")
    _assert(abs(s["notional"] - 2000.0) < 1e-9, "notional = units*entry")
    _assert(abs(s["reward_cash"] - 160.0) < 1e-9, "reward_cash = units*(TP-entry)")
    _assert(abs(s["leverage"] - 0.2) < 1e-9, "leverage = notional/equity")
    _assert(abs(s["rr"] - 1.6) < 1e-9, "R:R carried from levels")


def test_size_for_risk_zero_stop_distance_is_safe():
    lv = fc.trade_levels({"P5": 100.0, "P50": 100.0, "P95": 100.0}, "long")
    s = fc.size_for_risk(lv, equity=10000.0, risk_pct=1.0)
    _assert(s["units"] == 0.0, "no stop distance -> no position (never divide by zero)")


def test_trade_levels_custom_entry():
    cone = {"P5": 95.0, "P50": 100.0, "P95": 108.0}
    r = fc.trade_levels(cone, "long", entry=101.0)
    _assert(r["entry"] == 101.0 and abs(r["risk"] - 6.0) < 1e-9, "custom entry shifts risk")


def test_conformal_delta_split_quantile():
    scores = [0.1, 0.2, 0.3, 0.4, 0.5]
    # level 0.5 -> idx = ceil(6*0.5)=3 -> 3rd smallest = 0.3
    _assert(abs(fc.conformal_delta(scores, 0.5) - 0.3) < 1e-12, "median-ish quantile")
    # level 0.9 -> idx = ceil(6*0.9)=6 > n -> clamp to max = 0.5
    _assert(abs(fc.conformal_delta(scores, 0.9) - 0.5) < 1e-12, "over-index clamps to max")
    _assert(fc.conformal_delta([], 0.9) == 0.0, "empty scores -> 0 delta")


def test_conformalize_band_guarantees_coverage():
    # A deliberately TOO-NARROW 90% band: realized lands outside on ~half the records.
    recs = []
    for i in range(20):
        y = 100.0 + (i - 10) * 0.5          # spread -5..+4.5 around S0
        recs.append(_scored(P5=99.0, P95=101.0, realized=y))   # band only [99,101]
    out = fc.conformalize_band(recs, "gaussian", "90")
    _assert(out["cover_raw"] < 0.9, f"raw band must under-cover, got {out['cover_raw']}")
    _assert(out["delta_frac"] > 0.0, "under-covering band must widen (delta>0)")
    _assert(out["cover_adj"] >= 0.9 - 1e-9,
            f"conformal correction must reach >=90% coverage, got {out['cover_adj']}")


def test_conformalize_band_can_tighten_when_overwide():
    # A band far wider than needed: every realized is well inside -> delta<=0 (tighten).
    recs = [_scored(P5=0.0, P95=200.0, realized=100.0 + (i - 5) * 0.1) for i in range(20)]
    out = fc.conformalize_band(recs, "gaussian", "90")
    _assert(out["cover_raw"] == 1.0, "over-wide band covers everything raw")
    _assert(out["delta_frac"] <= 0.0, "over-wide band should tighten (delta<=0)")


def test_conformal_validate_out_of_sample_split():
    # 40 records, deliberately too-narrow 90% band; temporal 70/30 split. The delta
    # learned on TRAIN must raise coverage on the held-out TEST (generalizes).
    recs = [_scored(P5=99.0, P95=101.0, realized=100.0 + (i % 21 - 10) * 0.5, made=i)
            for i in range(40)]
    v = fc.conformal_validate(recs, "gaussian", "90", train_frac=0.7)
    _assert(v["n_train"] == 28 and v["n_test"] == 12, "temporal 70/30 split")
    _assert(v["delta_frac"] > 0.0, "under-covering band -> positive train delta")
    _assert(v["cover_adj_test"] >= v["cover_raw_test"], "correction must not worsen OOS coverage")


def test_conformal_validate_thin_returns_none():
    recs = [_scored(P5=99.0, P95=101.0, realized=100.5, made=i) for i in range(4)]
    _assert(fc.conformal_validate(recs, "gaussian", "90") is None, "too few records -> None")


def test_aci_next_alpha_updates_toward_target():
    # Not covered at target miscoverage 0.1 -> alpha DECREASES (widen next interval).
    lo = fc.aci_next_alpha(0.10, 0.10, covered=False, gamma=0.05)
    _assert(lo < 0.10, "a miss must lower alpha (widen)")
    # Covered -> alpha INCREASES slightly (allow tightening).
    hi = fc.aci_next_alpha(0.10, 0.10, covered=True, gamma=0.05)
    _assert(hi > 0.10, "a hit must raise alpha (tighten)")
    _assert(0.0 <= fc.aci_next_alpha(0.0, 0.1, covered=False) <= 1.0, "alpha stays in [0,1]")


def test_apply_conformal_widening_moves_only_outer_quantiles():
    cone = {"P5": 95.0, "P25": 98.0, "P50": 100.0, "P75": 102.0, "P95": 105.0,
            "p_up": 0.5, "model": "gaussian"}
    out = fc.apply_conformal_widening(cone, delta90_frac=0.02, delta50_frac=0.01, S0=100.0)
    _assert(out["P5"] == 95.0 - 2.0 and out["P95"] == 105.0 + 2.0, "90% band widened by 2")
    _assert(out["P25"] == 98.0 - 1.0 and out["P75"] == 102.0 + 1.0, "50% band widened by 1")
    _assert(out["P50"] == 100.0 and out["p_up"] == 0.5, "median and p_up untouched")
    _assert(out["P5"] <= out["P25"] <= out["P50"] <= out["P75"] <= out["P95"], "stays ordered")


def test_conformal_report_groups_by_symbol_tf_horizon():
    recs = [_scored(P5=99.0, P95=101.0, realized=100.0 + (i - 10) * 0.4, made=i)
            for i in range(20)]
    rep = fc.conformal_report(recs, min_n=5)
    _assert("X|15|4" in rep, "grouped by symbol|tf|horizon")
    _assert("gaussian" in rep["X|15|4"], "model present")
    _assert("90" in rep["X|15|4"]["gaussian"], "90 band present")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
