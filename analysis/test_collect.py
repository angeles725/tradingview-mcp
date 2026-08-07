"""
Tests for the OHLCV collector. Stdlib only. Run:
    python analysis/test_collect.py
"""

import os
import tempfile

import collect as co


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _bar(t, close):
    return {"time": t, "open": close - 1, "high": close + 1,
            "low": close - 2, "close": close, "volume": 100}


def test_merge_dedups_and_sorts():
    existing = {}
    ordered, n_new, n_upd = co.merge(existing, [_bar(30, 3), _bar(10, 1), _bar(20, 2)])
    _assert([r["time"] for r in ordered] == [10, 20, 30], "must sort by time")
    _assert(n_new == 3 and n_upd == 0, f"new/upd wrong: {n_new}/{n_upd}")
    # merging overlapping window adds only the genuinely new bar
    existing = {r["time"]: r for r in ordered}
    ordered2, n_new2, n_upd2 = co.merge(existing, [_bar(20, 2), _bar(40, 4)])
    _assert(n_new2 == 1 and n_upd2 == 0, f"overlap should add 1: {n_new2}/{n_upd2}")
    _assert(len(ordered2) == 4, "total must be 4 after overlap merge")


def test_repeated_timestamp_updates_forming_bar():
    existing = {r["time"]: r for r in co.merge({}, [_bar(10, 1)])[0]}
    # same timestamp, different close (the last live bar kept forming)
    ordered, n_new, n_upd = co.merge(existing, [_bar(10, 5)])
    _assert(n_new == 0 and n_upd == 1, f"should update not append: {n_new}/{n_upd}")
    _assert(ordered[0]["close"] == 5.0, "latest pull must win for a forming bar")


def test_save_load_roundtrip_and_emit():
    with tempfile.TemporaryDirectory() as d:
        path = co.store_path(d, "OANDA:XAUUSD", "15")
        rows, _, _ = co.merge({}, [_bar(10, 1), _bar(20, 2)])
        co.save_store(path, rows)
        _assert(os.path.exists(path), "store file must exist")
        reload = co.load_store(path)
        _assert(set(reload) == {10, 20}, "reload keys mismatch")
        _assert(reload[20]["close"] == 2.0, "reload value mismatch")
        # symbol ':' must be sanitized into the filename
        _assert("OANDA_XAUUSD_15.csv" in path, f"unsafe filename: {path}")


def test_atomic_save_no_partial_on_reopen():
    with tempfile.TemporaryDirectory() as d:
        path = co.store_path(d, "X", "5")
        co.save_store(path, co.merge({}, [_bar(1, 1)])[0])
        co.save_store(path, co.merge(co.load_store(path), [_bar(2, 2)])[0])
        _assert(set(co.load_store(path)) == {1, 2}, "second save must extend, not corrupt")
        _assert(not os.path.exists(path + ".tmp"), "no leftover temp file")


def test_is_stale_detects_zero_range_and_volume():
    ok = {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100}
    _assert(not co.is_stale(ok), "a normal bar is not stale")
    _assert(co.is_stale({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100}),
            "zero-range (high==low) bar is stale")
    _assert(co.is_stale({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 0}),
            "zero-volume bar is stale")
    _assert(co.is_stale({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}),
            "missing volume is stale")


def test_valid_ohlc_predicate():
    _assert(co.valid_ohlc({"open": 4, "high": 6, "low": 3, "close": 5}),
            "a normal bar must be valid")
    _assert(not co.valid_ohlc({"open": 5, "high": 3, "low": 6, "close": 5}),
            "high < low must be rejected")
    _assert(not co.valid_ohlc({"open": 5, "high": 5, "low": 4, "close": 9}),
            "close above high must be rejected")
    _assert(not co.valid_ohlc({"open": 5, "high": 5, "low": -1, "close": 5}),
            "negative price must be rejected")
    _assert(not co.valid_ohlc({"open": 5, "high": float("inf"), "low": 4, "close": 5}),
            "non-finite price must be rejected")


def test_contiguity_counts_session_gaps():
    # regular 60s bars with two big jumps (weekend/session gaps)
    times = [0, 60, 120, 180, 100000, 100060, 100120, 500000, 500060]
    n_gaps, step = co._contiguity(times)
    _assert(step == 60, f"median step should be 60s, got {step}")
    _assert(n_gaps == 2, f"expected 2 session gaps, got {n_gaps}")
    # a perfectly contiguous series has no gaps
    n0, s0 = co._contiguity([0, 60, 120, 180, 240])
    _assert(n0 == 0, f"contiguous series must report 0 gaps, got {n0}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
