"""
Gate-logic tests for the decision engine. Run:
    <venv>/python analysis/test_decide.py

The engine must default to NO-TRADE and only propose a trade when every gate
passes. These tests pin each gate's veto and the full BUY path.
"""

import numpy as np

import decide as d
from decide import Config


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _trending_series(n=200, seed=0):
    """Upward drift with positive-autocorrelation (momentum) returns, so the
    series is significantly trending, regime trend-up, and VR>1."""
    rng = np.random.default_rng(seed)
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = 0.5 * e[i - 1] + rng.normal(0, 0.3)
    ret = 0.004 + e * 0.01
    c = 100 * np.exp(np.cumsum(ret))
    o = c * (1 - rng.normal(0, 0.0005, n))
    h = np.maximum(o, c) * (1 + abs(rng.normal(0, 0.0008, n)))
    l = np.minimum(o, c) * (1 - abs(rng.normal(0, 0.0008, n)))
    return o, h, l, c


def _chop_series(n=200, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 + rng.normal(0, 1.0, n)          # noise around a level
    o = c + rng.normal(0, 0.2, n)
    h = np.maximum(o, c) + abs(rng.normal(0, 0.3, n))
    l = np.minimum(o, c) - abs(rng.normal(0, 0.3, n))
    return o, h, l, c


def test_chop_is_no_trade_gate_a():
    o, h, l, c = _chop_series()
    st = d.decide(o, h, l, c, Config())
    _assert(st.action == "NO-TRADE", f"chop must be NO-TRADE, got {st.action}")
    _assert(st.gates[0]["name"] == "A_direction" and not st.gates[0]["passed"],
            "Gate A should veto chop")


def test_trend_passes_gate_a():
    o, h, l, c = _trending_series()
    # isolate Gate A by forcing a favourable edge and trivial R:R
    st = d.decide(o, h, l, c, Config(min_rr=0.0),
                  edge_override=(True, "forced edge"))
    _assert(st.gates[0]["passed"], f"trend must pass Gate A: {st.gates[0]['detail']}")
    _assert(st.action == "BUY", f"trend + edge + trivial RR -> BUY, got {st.action}")


def test_no_edge_is_no_trade_gate_b():
    o, h, l, c = _trending_series()
    st = d.decide(o, h, l, c, Config(min_rr=0.0),
                  edge_override=(False, "no edge"))
    _assert(st.action == "NO-TRADE", "no edge must be NO-TRADE")
    _assert(st.gates[-1]["name"] == "B_edge" and not st.gates[-1]["passed"],
            "Gate B should veto when no edge")


def test_bad_rr_is_no_trade_gate_c():
    o, h, l, c = _trending_series()
    st = d.decide(o, h, l, c, Config(min_rr=99.0),
                  edge_override=(True, "forced edge"))
    _assert(st.action == "NO-TRADE", "impossible R:R must be NO-TRADE")
    _assert(st.gates[-1]["name"] == "C_risk_reward" and not st.gates[-1]["passed"],
            "Gate C should veto bad R:R")


def test_sizing_risks_fixed_fraction():
    o, h, l, c = _trending_series()
    cfg = Config(min_rr=0.0, risk_frac=0.01, equity=10_000.0)
    st = d.decide(o, h, l, c, cfg, edge_override=(True, "forced edge"))
    _assert(st.action == "BUY", "expected a BUY to check sizing")
    # risk_cash must equal risk_frac * equity, and size*stop_distance ~ risk_cash
    _assert(abs(st.risk_cash - 100.0) < 1e-6, f"risk_cash {st.risk_cash}")
    implied = st.size_units * abs(st.entry - st.stop)
    _assert(abs(implied - st.risk_cash) < 1e-6, "size must risk exactly risk_cash")


def test_edge_precondition_ignores_future_bars():
    # The historical feedback must not leak the future: the edge precondition used
    # to authorize a trade at bar t may only be validated on bars STRICTLY BEFORE
    # t. Scrambling every bar at or after t must not change it.
    o, h, l, c = _trending_series(200, seed=0)
    cfg = Config()
    t = 120
    ref = d._edge_precondition(o, h, l, c, t, cfg)
    o2, h2, l2, c2 = o.copy(), h.copy(), l.copy(), c.copy()
    o2[t:] *= 2; h2[t:] *= 2; l2[t:] *= 2; c2[t:] *= 2      # corrupt the future
    scr = d._edge_precondition(o2, h2, l2, c2, t, cfg)
    _assert(ref == scr, f"edge precondition at t leaked bars >= t: {ref} != {scr}")


def test_simulate_process_runs_without_lookahead():
    # The whole feedback loop must run and report an honest verdict on a walk.
    o, h, l, c = _trending_series(220, seed=2)
    out = d.simulate_process(o, h, l, c, Config())
    _assert(set(out["decisions"]) == {"BUY", "SELL", "NO-TRADE"}, "decisions tallied")
    _assert("expanding edge@" in out["edge_precondition"],
            f"expected expanding-window precondition, got {out['edge_precondition']}")
    _assert(out["verdict"] in ("edge", "no-edge", "thin-sample", "no-trades"),
            f"unexpected verdict {out['verdict']}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
