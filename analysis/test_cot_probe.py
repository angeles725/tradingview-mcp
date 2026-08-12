"""
Tests for the COT edge probe's pure logic (cot_probe.py). The network fetch is
not unit-tested; the signal/alignment math is.

Run with:
    <venv>/python analysis/test_cot_probe.py
"""
import datetime

import numpy as np

import cot_probe as cp


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _dates(n, start=datetime.date(2015, 1, 6)):
    return [(start + datetime.timedelta(days=7 * i)).isoformat() for i in range(n)]


def test_cot_index_monotonic_endpoints():
    net = np.arange(300, dtype=float)           # strictly increasing
    idx = cp.cot_index(net, lookback=156)
    _assert(np.isnan(idx[:155]).all(), "warm-up must be NaN")
    _assert(abs(idx[-1] - 1.0) < 1e-9, f"top of an increasing series -> 1.0, got {idx[-1]}")
    dec = cp.cot_index(-net, lookback=156)
    _assert(abs(dec[-1] - 0.0) < 1e-9, f"bottom of a decreasing series -> 0.0, got {dec[-1]}")


def test_build_records_emits_extremes_and_aligns_forward():
    n = 300
    dates = _dates(n)
    cot = [{"date": d, "comm_net": float(i), "noncomm_net": 0.0}
           for i, d in enumerate(dates)]
    ctimes = cp._iso_to_unix(dates)
    closes = 100.0 + np.arange(n, dtype=float)   # strictly rising price
    recs = cp.build_records(cot, "comm_net", lookback=156, up_thresh=0.8,
                            down_thresh=0.2, closes=closes, ctimes=ctimes,
                            horizon=2, symbol="TEST")
    _assert(len(recs) > 50, f"increasing net -> many up extremes, got {len(recs)}")
    _assert(all(r["bias"] == "up" for r in recs), "increasing net must be all up-calls")
    _assert(all(r["hit"] == 1 for r in recs), "rising price -> every up-call hits")


def test_build_records_no_signal_when_flat():
    n = 300
    dates = _dates(n)
    cot = [{"date": d, "comm_net": 5.0, "noncomm_net": 0.0} for d in dates]  # constant
    ctimes = cp._iso_to_unix(dates)
    closes = 100.0 + np.zeros(n)
    recs = cp.build_records(cot, "comm_net", lookback=156, up_thresh=0.8,
                            down_thresh=0.2, closes=closes, ctimes=ctimes,
                            horizon=2, symbol="TEST")
    _assert(len(recs) == 0, f"flat positioning -> no extreme signal, got {len(recs)}")


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run()
