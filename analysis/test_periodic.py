"""Tests for the periodic (monthly/weekly) forecast. Run under the scipy venv:
    <venv>/python analysis/test_periodic.py"""
import numpy as np

import periodic as pf


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _bars(n=200, seed=0, step=86400, t0=1_700_000_000):
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
    return [{"time": t0 + i * step, "open": float(c[i]), "high": float(c[i] * 1.01),
             "low": float(c[i] * 0.99), "close": float(c[i]), "volume": 1} for i in range(n)]


def test_build_month_shapes_record_with_cone_levels():
    rec = pf.build(_bars(200), "OANDA:XAUUSD", "D", "month", side="long")
    _assert(rec["period"] == "month" and rec["horizon_bars"] == 22, "month default horizon 22 (D)")
    _assert(rec["target_unix"] == rec["made_at_unix"] + rec["bar_step_sec"] * 22, "target = made + step*h")
    lv = rec["levels"]
    _assert(lv["stop_loss"] == rec["cone"]["P5"] and lv["take_profit"] == rec["cone"]["P95"],
            "long SL/TP come from the cone P5/P95")
    _assert(lv["rr"] > 0 and lv["side"] == "long", "R:R computed, side honored")


def test_build_week_horizon_and_review_field():
    rec = pf.build(_bars(200), "OANDA:XAUUSD", "D", "week", side="auto")
    _assert(rec["horizon_bars"] == 5, "week default horizon 5 (D)")
    _assert("last_week_review" in rec, "weekly record carries a review field (may be None)")
    _assert(rec["levels"]["side"] in ("long", "short"), "auto side resolves to long/short")


def test_horizon_override():
    rec = pf.build(_bars(120), "X", "D", "month", side="long", horizon=10)
    _assert(rec["horizon_bars"] == 10, "explicit horizon overrides the default")


def test_build_embeds_confluence():
    rec = pf.build(_bars(200), "OANDA:XAUUSD", "D", "week", side="auto")
    conf = rec.get("confluence")
    _assert(conf is not None, "periodic record embeds the confluence read")
    _assert("fib_bull" in conf and "scenarios" in conf and "rsi" in conf,
            "confluence carries fibs, scenarios and RSI")
    _assert(set(("bull", "base", "bear")) <= set(conf["scenarios"]), "bull/base/bear panoramas")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
