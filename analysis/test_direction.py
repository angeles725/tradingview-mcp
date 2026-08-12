"""
Behavior tests for the multi-timeframe directional bias (direction.py).

The properties that matter for HONESTY:
  1. A clean uptrend on a high TF must read "up" with real confidence.
  2. A clean downtrend must read "down".
  3. Pure noise must read "flat" (never a coin-flip arrow).
  4. The SAME signal on 1m must carry LESS confidence than on the daily
     (the validated intraday no-edge, encoded as TF_RELIABILITY).
  5. Confidence is capped below 1.0 — the tool never claims certainty.
  6. aggregate() rewards higher-timeframe alignment.

Run with:
    <venv>/python analysis/test_direction.py
"""
import numpy as np

import direction as d


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _synth(closes):
    """Build OHLCV arrays from a close path (flat range, unit volume, unit dt)."""
    c = np.asarray(closes, dtype=float)
    o = np.concatenate(([c[0]], c[:-1]))
    h = np.maximum(o, c) * 1.001
    l = np.minimum(o, c) * 0.999
    v = np.ones_like(c) * 1000.0
    t = np.arange(c.size, dtype=float)
    return o, h, l, c, v, t


def test_clean_uptrend_reads_up():
    c = 100.0 * np.exp(np.cumsum(np.full(260, 0.002)))  # steady drift up
    o, h, l, cc, v, t = _synth(c)
    rec = d.bias_from_bars(o, h, l, cc, v, t, "D")
    _assert(rec["bias"] == "up", f"clean uptrend must be up, got {rec['bias']}")
    _assert(rec["confidence"] > 0.3, f"uptrend confidence too low: {rec['confidence']}")


def test_clean_downtrend_reads_down():
    c = 100.0 * np.exp(np.cumsum(np.full(260, -0.002)))
    o, h, l, cc, v, t = _synth(c)
    rec = d.bias_from_bars(o, h, l, cc, v, t, "D")
    _assert(rec["bias"] == "down", f"clean downtrend must be down, got {rec['bias']}")


def test_pure_noise_reads_flat():
    rng = np.random.default_rng(42)
    c = 100.0 + np.cumsum(rng.normal(0, 0.05, 260))  # driftless random walk
    o, h, l, cc, v, t = _synth(c)
    rec = d.bias_from_bars(o, h, l, cc, v, t, "15")
    _assert(rec["bias"] == "flat",
            f"driftless noise must be flat, got {rec['bias']} conf={rec['confidence']}")


def test_intraday_confidence_below_daily_for_same_signal():
    c = 100.0 * np.exp(np.cumsum(np.full(260, 0.002)))
    o, h, l, cc, v, t = _synth(c)
    daily = d.bias_from_bars(o, h, l, cc, v, t, "D")
    m1 = d.bias_from_bars(o, h, l, cc, v, t, "1")
    _assert(m1["confidence"] < daily["confidence"],
            f"1m conf {m1['confidence']} must be < daily {daily['confidence']}")


def test_confidence_never_claims_certainty():
    c = 100.0 * np.exp(np.cumsum(np.full(300, 0.01)))  # extreme monotone trend
    o, h, l, cc, v, t = _synth(c)
    rec = d.bias_from_bars(o, h, l, cc, v, t, "W")
    _assert(rec["confidence"] <= d.CONF_CEIL,
            f"confidence {rec['confidence']} must be capped at {d.CONF_CEIL}")


def test_aggregate_counts_and_overall():
    recs = [
        {"tf": "M", "bias": "up", "confidence": 0.7},
        {"tf": "W", "bias": "up", "confidence": 0.6},
        {"tf": "D", "bias": "up", "confidence": 0.5},
        {"tf": "60", "bias": "flat", "confidence": 0.1},
        {"tf": "15", "bias": "flat", "confidence": 0.05},
        {"tf": "1", "bias": "down", "confidence": 0.08},
    ]
    ag = d.aggregate(recs)
    _assert(ag["overall"] == "up", f"3 strong up TFs must aggregate up, got {ag}")
    _assert(ag["n_up"] == 3 and ag["n_down"] == 1 and ag["n_flat"] == 2, f"counts wrong: {ag}")
    _assert(ag["hi_tf_up"] == 3 and ag["n_hi_tf"] == 3, f"hi-tf tally wrong: {ag}")


def test_short_series_rejected():
    o, h, l, cc, v, t = _synth([1, 2, 3])
    try:
        d.bias_from_bars(o, h, l, cc, v, t, "15")
    except ValueError:
        return
    raise AssertionError("expected ValueError on <5 bars")


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run()
