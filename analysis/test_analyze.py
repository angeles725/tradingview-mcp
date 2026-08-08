"""
Leakage guard for the conditional-probability builder. The failure this catches
is real: a condition that references bar t+1 prints a fake 100% edge. Run with:
    <venv>/python analysis/test_analyze.py
"""

import numpy as np

import quant as q
from analyze import build_conditions


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_no_condition_perfectly_predicts_target():
    """
    On a random walk NO honest condition can hit rate ~1.0 with a large sample.
    A perfect rate on a thick bucket means the mask leaked the target.
    """
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 1, 400))
    opens = closes - rng.normal(0, 0.5, 400)
    rsi = q.rsi_wilder(closes, 14)
    conds, target_up = build_conditions(closes, opens, rsi, q.log_returns(closes))
    baseline = float(np.mean(target_up))
    for name, mask in conds.items():
        c = q.conditional_next_up(name, mask, target_up, baseline)
        if c.n >= 30:
            _assert(c.rate < 0.95,
                    f"LEAKAGE: '{name}' rate={c.rate:.2f} on n={c.n} (looks like lookahead)")


def test_conditions_and_target_length_align():
    closes = np.arange(1, 51, dtype=float)
    opens = closes - 0.3
    rsi = q.rsi_wilder(closes, 14)
    conds, target_up = build_conditions(closes, opens, rsi, q.log_returns(closes))
    for name, mask in conds.items():
        _assert(mask.size == target_up.size,
                f"'{name}' length {mask.size} != target {target_up.size}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
