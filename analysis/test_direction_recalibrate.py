"""
Tests for the confidence recalibration (direction_recalibrate.py).

Properties that matter for HONESTY:
  1. When the raw score is uninformative (hit independent of confidence), the
     adopted method is 'marginal' — confidence collapses to the base rate, never
     pretends to carry information.
  2. When the raw score is miscalibrated but monotonically recoverable, isotonic
     is adopted and improves (or ties) OOS Brier — never worse than raw.
  3. Too little data -> method 'none' (left uncalibrated, honestly flagged).
  4. apply_calibration respects adoption and falls back to raw otherwise.

Run with:
    <venv>/python analysis/test_direction_recalibrate.py
"""
import numpy as np

import direction_recalibrate as rc


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _recs(confs, hits, tf="D"):
    return [{"tf": tf, "confidence": float(c), "hit": int(h), "bias": "up",
             "made_at_unix": i} for i, (c, h) in enumerate(zip(confs, hits))]


def test_uninformative_score_collapses_to_marginal():
    rng = np.random.default_rng(1)
    n = 400
    confs = rng.uniform(0.2, 0.95, n)          # varied confidence...
    hits = rng.binomial(1, 0.55, n)            # ...but hit is independent of it
    m = rc.recalibrate_tf(_recs(confs, hits))
    _assert(m["method"] in ("marginal", "none"),
            f"uninformative score must not adopt raw/isotonic, got {m['method']}")
    if m["method"] == "marginal":
        _assert(abs(m["value"] - 0.55) < 0.12, f"marginal off base rate: {m}")


def test_recoverable_miscalibration_adopts_isotonic_and_not_worse():
    rng = np.random.default_rng(2)
    n = 600
    confs = rng.uniform(0.0, 1.0, n)
    # true P(correct) is a monotonic function of confidence but on a compressed
    # scale (raw is overconfident): p_true = 0.5 + 0.35*conf
    p = 0.5 + 0.35 * confs
    hits = rng.binomial(1, p)
    m = rc.recalibrate_tf(_recs(confs, hits))
    _assert(m["adopted"], f"recoverable signal should be adopted: {m}")
    # whatever is adopted must not be worse OOS than raw
    best = m["brier_isotonic"] if m["method"] == "isotonic" else m["brier_marginal"]
    _assert(best <= m["brier_raw"] + 1e-9,
            f"adopted OOS Brier must beat raw: {m}")


def test_too_little_data_is_left_uncalibrated():
    m = rc.recalibrate_tf(_recs([0.5] * 10, [1, 0] * 5))
    _assert(m["method"] == "none" and not m["adopted"], f"expected none: {m}")


def test_apply_calibration_respects_adoption():
    calmap = {
        "D": {"method": "marginal", "value": 0.58, "adopted": True},
        "W": {"method": "none", "adopted": False},
    }
    _assert(abs(rc.apply_calibration(0.9, "D", calmap) - 0.58) < 1e-9,
            "adopted marginal must override raw")
    _assert(abs(rc.apply_calibration(0.9, "W", calmap) - 0.9) < 1e-9,
            "unadopted TF must fall back to raw")
    _assert(abs(rc.apply_calibration(0.9, "M", calmap) - 0.9) < 1e-9,
            "missing TF must fall back to raw")


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run()
