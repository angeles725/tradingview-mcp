"""
Tests for the honest backtest engine. Run:
    <venv>/python analysis/test_backtest.py
"""

import numpy as np

import quant as q
import backtest as bt


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_fills_are_next_open_no_lookahead():
    # opens strictly increasing by 1; a long held 1 bar must earn exactly
    # ln(open[t+2]/open[t+1]) — never touching bar t's own price.
    o = np.arange(10, 20, dtype=float)
    c = o + 0.5
    signal = np.zeros(o.size, dtype=bool)
    signal[3] = True                       # signal on bar 3
    net, cost = bt.simulate(signal, o, c, hold=1, cost_bps_per_side=0.0)
    expected = np.log(o[5] / o[4])         # enter open[4], exit open[5]
    _assert(net.size == 1, "one trade expected")
    _assert(abs(net[0] - expected) < 1e-12,
            f"fill leaked: got {net[0]}, expected open[4]->open[5] {expected}")


def test_signal_on_last_bars_is_dropped_not_peeked():
    o = np.arange(10, 20, dtype=float)
    c = o + 0.5
    signal = np.zeros(o.size, dtype=bool)
    signal[-1] = True                      # no room for entry+hold
    net, _ = bt.simulate(signal, o, c, hold=2, cost_bps_per_side=0.0)
    _assert(net.size == 0, "trade with no forward bars must be dropped")


def test_cost_monotonically_reduces_expectancy():
    rng = np.random.default_rng(0)
    o = 100 + np.cumsum(rng.normal(0, 1, 300))
    c = o + rng.normal(0, 0.2, 300)
    signal = rng.random(300) < 0.3
    e0 = bt.compute_stats(bt.simulate(signal, o, c, 5, 0.0)[0]).expectancy_ret
    e1 = bt.compute_stats(bt.simulate(signal, o, c, 5, 2.0)[0]).expectancy_ret
    _assert(e1 < e0, "higher cost must lower net expectancy")


def test_thin_sample_flagged():
    o = np.arange(10, 50, dtype=float)
    c = o + 0.5
    signal = np.zeros(o.size, dtype=bool)
    signal[[3, 7, 11]] = True              # only 3 trades
    stats = bt.compute_stats(bt.simulate(signal, o, c, 2, 0.0)[0])
    _assert(stats.verdict == "thin-sample", f"got {stats.verdict}")


def test_ema_tracks_and_warms_up():
    c = np.arange(1, 21, dtype=float)
    e = q.ema(c, 5)
    _assert(np.isnan(e[:4]).all(), "warm-up must be NaN")
    _assert(not np.isnan(e[4]), "EMA must start at period-1")
    _assert(e[-1] < c[-1], "rising series: EMA lags below price")


def test_no_free_edge_on_random_walk():
    # On a pure random walk no rule should show a significant NET edge.
    rng = np.random.default_rng(11)
    o = 100 + np.cumsum(rng.normal(0, 1, 300))
    h = o + 0.5; l = o - 0.5; c = o + rng.normal(0, 0.2, 300)
    sig = bt.rule_ema_trend(o, h, l, c, period=20)
    net, cost = bt.simulate(sig, o, c, 8, 1.0)
    stats = bt.compute_stats(net)
    _assert(stats.verdict != "edge",
            f"random walk must NOT produce a net edge, got {stats.verdict} "
            f"exp={stats.expectancy_bps:.2f} CI={stats.ci95_ret}")


def test_return_entries_align_with_trades():
    o = np.arange(10, 40, dtype=float)
    c = o + 0.5
    signal = np.zeros(o.size, dtype=bool)
    signal[[3, 10, 20]] = True
    net, entries, cost = bt.simulate(signal, o, c, hold=2, cost_bps_per_side=0.0,
                                     return_entries=True)
    _assert(entries.size == net.size, "entries must align 1:1 with trades")
    # non-overlapping, well-spaced signals -> entry = signal_bar + 1
    _assert(list(entries) == [4, 11, 21], f"entries misaligned: {list(entries)}")


def test_verdict_uses_block_bootstrap_ci_not_iid():
    # Non-overlapping trades still cluster by regime, so the i.i.d. CI under-covers.
    # The honest serial-dependence-aware block CI must DRIVE the verdict and be the
    # reported interval — not the narrower i.i.d. one the engine used to judge on.
    rng = np.random.default_rng(5)
    net = rng.normal(0.0008, 0.01, 80)          # n >= min_n, small positive mean
    stats = bt.compute_stats(net)
    block_ci = q.bootstrap_mean_ci_block(net)
    _assert(stats.ci95_ret == block_ci,
            f"reported CI must be the block CI {block_ci}, got {stats.ci95_ret}")
    expected = "edge" if block_ci[0] > 0 else "no-edge"
    _assert(stats.verdict == expected,
            f"verdict must follow block CI: expected {expected}, got {stats.verdict}")


def test_ema_rule_mirrors_condition_for_short():
    # A short setup must test the DOWN condition (c < ema), not the long one.
    # Otherwise Gate B measures "short whenever price is ABOVE its EMA" — a
    # counter-trend signal that has nothing to do with a downtrend edge.
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 1, 200))     # crosses its EMA both ways
    o = c.copy(); h = c + 0.5; l = c - 0.5
    e = q.ema(c, 20)
    defined = ~np.isnan(e)
    long_sig = bt.rule_ema_trend(o, h, l, c, period=20, direction=1)
    short_sig = bt.rule_ema_trend(o, h, l, c, period=20, direction=-1)
    _assert(np.array_equal(long_sig[defined], (c > e)[defined]),
            "long signal must be c>ema")
    _assert(np.array_equal(short_sig[defined], (c < e)[defined]),
            "short signal must mirror to c<ema")
    _assert(not np.any(long_sig & short_sig),
            "long and short signals must be disjoint")
    _assert(short_sig.sum() > 0, "short signal must fire somewhere on this series")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
