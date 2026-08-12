"""
Tests for the cone coverage flag (cone_coverage.py).

Properties that matter for HONESTY:
  1. A cone whose 90% band actually covers ~90% is 'reliable'.
  2. A cone whose band covers far below 90% is 'too-tight' (the dangerous case,
     it must be flagged so a stop is given more room).
  3. A cone covering far above 90% is 'too-wide'.
  4. Too few records -> 'insufficient' (no false verdict).
  5. warning_line only speaks for the actionable verdicts.

Run with:
    <venv>/python analysis/test_cone_coverage.py
"""
import cone_coverage as cc
import forecast as fc


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _rec(symbol, tf, lo, hi, y, i, s0=100.0):
    """A scored cone record, built through fc.score_record exactly as backfill.py
    does (so realized.models.<m>.in_90 exists). made_at/target are spaced so the
    independent-subset filter keeps every record (non-overlapping)."""
    made = i * 1_000_000
    rec = {"symbol": symbol, "tf": tf, "horizon_bars": 5, "S0": s0,
           "made_at_unix": made, "target_unix": made + 500_000,
           "cones": {"gaussian": {"P5": lo, "P25": lo, "P50": (lo + hi) / 2,
                                  "P75": hi, "P95": hi, "p_up": 0.5, "model": "gaussian"}},
           "realized": None}
    return fc.score_record(rec, float(y))


def _series(symbol, tf, cover_frac, n=60):
    """n records where a `cover_frac` fraction fall inside the 90% band."""
    recs = []
    n_in = int(round(cover_frac * n))
    for i in range(n):
        if i < n_in:
            recs.append(_rec(symbol, tf, 90.0, 110.0, 100.0, i))   # inside
        else:
            recs.append(_rec(symbol, tf, 90.0, 110.0, 130.0, i))   # outside (above P95)
    return recs


def test_reliable_when_near_nominal():
    m = cc.build_coverage_map(_series("SYM", "D", 0.90))
    _assert(m["SYM|D"]["verdict"] == "reliable", f"~90% must be reliable: {m}")


def test_too_tight_flagged():
    m = cc.build_coverage_map(_series("GOLD", "D", 0.78))
    _assert(m["GOLD|D"]["verdict"] == "too-tight", f"78% cover must be too-tight: {m}")
    w = cc.warning_line("GOLD", "D", m)
    _assert("ESTRECHA" in w and "[!]" in w, f"too-tight must warn: {w!r}")


def test_too_wide_flagged():
    m = cc.build_coverage_map(_series("SYM", "W", 0.99))
    _assert(m["SYM|W"]["verdict"] == "too-wide", f"99% cover must be too-wide: {m}")


def test_insufficient_when_small():
    m = cc.build_coverage_map(_series("SYM", "M", 0.90, n=10))
    _assert(m["SYM|M"]["verdict"] == "insufficient", f"n=10 must be insufficient: {m}")
    _assert(cc.warning_line("SYM", "M", m) == "", "insufficient must not warn")


def test_reliable_and_unknown_are_silent():
    m = cc.build_coverage_map(_series("SYM", "D", 0.90))
    _assert(cc.warning_line("SYM", "D", m) == "", "reliable must be silent")
    _assert(cc.warning_line("NOPE", "D", m) == "", "unknown must be silent")


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run()
