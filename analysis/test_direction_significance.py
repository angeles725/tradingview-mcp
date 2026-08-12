"""
Tests for the directional skill significance test (direction_significance.py).

Properties that matter for HONESTY:
  1. A predictor with genuine skill (calls align with outcomes beyond the base
     rate) is flagged real_skill=True with a positive skill CI and small p.
  2. A predictor that just echoes the majority class (always up in an up market)
     shows ~zero skill and real_skill=False — the base-rate trap is caught.
  3. Random predictions show skill CI spanning 0 and a large permutation p.

Run with:
    <venv>/python analysis/test_direction_significance.py
"""
import numpy as np

import direction_significance as ds


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _recs(preds, realized, symbols):
    out = []
    for i, (p, r, s) in enumerate(zip(preds, realized, symbols)):
        hit = 1 if (p == np.sign(r)) else 0
        out.append({"tf": "M", "bias": "up" if p > 0 else "down",
                    "confidence": 0.7, "realized_dir": int(r), "hit": hit,
                    "symbol": s})
    return out


def test_genuine_skill_is_detected():
    rng = np.random.default_rng(0)
    n = 400
    realized = rng.choice([-1, 1], n)
    # predictions correct 75% of the time -> real skill above 50% base
    preds = np.where(rng.random(n) < 0.75, realized, -realized)
    syms = rng.choice([f"S{i}" for i in range(10)], n)
    res = ds.skill_test(_recs(preds, realized, syms), n_boot=1500)
    _assert(res["real_skill"], f"genuine skill must be detected: {res}")
    _assert(res["skill_ci95"][0] > 0, f"CI lower bound must be >0: {res}")


def test_base_rate_trap_shows_no_skill():
    rng = np.random.default_rng(1)
    n = 400
    realized = np.where(rng.random(n) < 0.65, 1, -1)   # 65% up market
    preds = np.ones(n)                                 # always predict up
    syms = rng.choice([f"S{i}" for i in range(10)], n)
    res = ds.skill_test(_recs(preds, realized, syms), n_boot=1500)
    _assert(not res["real_skill"], f"always-up must show no skill: {res}")
    _assert(abs(res["skill"]) < 0.05, f"skill should be ~0 vs benchmark: {res}")


def test_random_predictions_span_zero():
    rng = np.random.default_rng(2)
    n = 400
    realized = rng.choice([-1, 1], n)
    preds = rng.choice([-1, 1], n)
    syms = rng.choice([f"S{i}" for i in range(10)], n)
    res = ds.skill_test(_recs(preds, realized, syms), n_boot=1500)
    _assert(not res["real_skill"], f"random must not be real skill: {res}")
    _assert(res["p_permutation"] > 0.05, f"random perm p must be large: {res}")


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run()
