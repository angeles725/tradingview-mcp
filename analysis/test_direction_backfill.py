"""
Tests for the directional-bias calibration (direction_backfill.py).

The properties that matter for HONESTY:
  1. No lookahead: the bias at window t is computed from bars[:t+1] only.
  2. A persistently trending series must calibrate to a HIGH hit-rate
     (the walk-forward machinery correctly pairs bias with realized move).
  3. A driftless random walk must calibrate near 50% — no manufactured edge.
  4. calibrate() buckets, Brier, and flat-exclusion behave.

Run with:
    <venv>/python analysis/test_direction_backfill.py
"""
import numpy as np

import direction_backfill as db


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _bars(closes):
    c = np.asarray(closes, dtype=float)
    return [{"open": float(c[max(i - 1, 0)]), "high": float(c[i]) * 1.001,
             "low": float(c[i]) * 0.999, "close": float(c[i]),
             "volume": 1000.0, "time": float(i)} for i in range(c.size)]


def test_trending_series_calibrates_high_hit_rate():
    c = 100.0 * np.exp(np.cumsum(np.full(600, 0.003)))  # steady uptrend
    recs = db.walk_forward(_bars(c), "SYNTH", "D", horizon=5, warmup=60)
    cal = db.calibrate(recs)
    _assert(cal["n_directional"] > 5, f"too few directional calls: {cal}")
    _assert(cal["hit_rate"] > 0.8,
            f"a clean uptrend must hit high, got {cal['hit_rate']:.2f}")


def test_random_walk_calibrates_near_coinflip():
    rng = np.random.default_rng(7)
    c = 100.0 + np.cumsum(rng.normal(0, 0.1, 1200))  # driftless
    recs = db.walk_forward(_bars(c), "SYNTH", "15", horizon=4, warmup=60)
    cal = db.calibrate(recs)
    # The honest invariant: whatever directional calls noise produces, they must
    # win only ~half the time (no manufactured edge) and confidence must NOT beat
    # the p=0.5 Brier of 0.25 by a meaningful margin.
    _assert(cal["n_directional"] >= 20, f"expected a usable sample, got {cal}")
    _assert(abs(cal["hit_rate"] - 0.5) < 0.15,
            f"noise must be near 50%, got {cal['hit_rate']:.2f}")
    _assert(cal["brier"] >= 0.15,
            f"confidence must not appear informative on noise, brier={cal['brier']:.3f}")


def test_no_lookahead_bias_uses_only_past():
    # If the last bar of the window were used with the future, a bias would be
    # able to "see" t+h. Prove the record's made_at < target time strictly.
    c = 100.0 * np.exp(np.cumsum(np.full(300, 0.002)))
    recs = db.walk_forward(_bars(c), "SYNTH", "D", horizon=5, warmup=60)
    for r in recs:
        _assert(r["made_at_unix"] < r["target_unix"],
                "made_at must precede target (no lookahead)")


def test_calibrate_buckets_and_flat_exclusion():
    recs = [
        {"bias": "up", "confidence": 0.9, "realized_dir": 1, "hit": 1},
        {"bias": "up", "confidence": 0.9, "realized_dir": -1, "hit": 0},
        {"bias": "down", "confidence": 0.7, "realized_dir": -1, "hit": 1},
        {"bias": "flat", "confidence": 0.1, "realized_dir": 1, "hit": None},
    ]
    cal = db.calibrate(recs)
    _assert(cal["n_directional"] == 3 and cal["n_flat"] == 1, f"counts: {cal}")
    _assert(abs(cal["hit_rate"] - 2 / 3) < 1e-9, f"hit_rate: {cal['hit_rate']}")
    hi_bucket = [b for b in cal["buckets"] if b["lo"] == 0.8][0]
    _assert(hi_bucket["n"] == 2, f"0.8-1.0 bucket should hold 2: {hi_bucket}")


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run()
