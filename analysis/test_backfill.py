"""Tests for the backfill walk. Run under the scipy venv:
    <venv>/python analysis/test_backfill.py"""
import os
import tempfile

import numpy as np

import backfill as bf
import forecast as fc


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _bars(n=200, seed=0, step=900, t0=1_000_000):
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.004, n)))
    return [{"time": t0 + i * step, "open": c[i], "high": c[i] * 1.001,
             "low": c[i] * 0.999, "close": float(c[i]), "volume": 1} for i in range(n)]


def test_backfill_makes_non_overlapping_scored_records():
    bars = _bars(200, seed=1)
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "bf.jsonl")
        h, warmup = 4, 60
        made = bf.backfill_bars(bars, "OANDA:XAUUSD", "15", h, warmup, log)
        # non-overlapping windows from warmup..n-h stepping by h
        expected = len(range(warmup, len(bars) - h, h))
        _assert(made == expected, f"made {made}, expected {expected}")
        recs = fc.read_log(log)
        _assert(len(recs) == made, "one log line per forecast")
        _assert(all(r["symbol"] == "OANDA:XAUUSD" for r in recs), "symbol tagged")
        _assert(all(r["realized"] is not None for r in recs), "every record scored")
        # windows are non-overlapping: made_at spacing >= horizon*step
        mades = sorted(r["made_at_unix"] for r in recs)
        gaps = [b - a for a, b in zip(mades, mades[1:])]
        _assert(all(g >= h * 900 for g in gaps), f"windows must not overlap: {gaps[:3]}")


def test_backfill_too_few_bars_makes_nothing():
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "bf.jsonl")
        made = bf.backfill_bars(_bars(40), "X", "15", 4, 60, log)
        _assert(made == 0, "insufficient history yields no forecasts")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
