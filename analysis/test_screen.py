"""Unit tests for the pure parsing logic in screen.py (the CDP I/O is exercised
live, not here). Run under the scipy venv: <venv>/python analysis/test_screen.py"""
import screen as sc


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_parse_momentum_extracts_vr_z_r2_regime():
    ga = "trend NOT sig (R^2=0.77), regime=trend-up (want trend-up), VR4=1.01 (z=0.09)"
    m = sc._parse_momentum(ga, vr_z_floor=1.645)
    _assert(m["vr"] == 1.01, f"vr {m['vr']}")
    _assert(m["vr_z"] == 0.09, f"z {m['vr_z']}")
    _assert(m["r2"] == 0.77, f"r2 {m['r2']}")
    _assert(m["regime"] == "trend-up", f"regime {m['regime']}")
    # VR>1 but z below the floor -> NOT a momentum edge
    _assert(m["momentum"] is False, "insignificant z must not count as momentum")


def test_parse_momentum_flags_real_edge():
    ga = "trend sig (R^2=0.55), regime=trend-up (want trend-up), VR4=1.20 (z=2.00)"
    m = sc._parse_momentum(ga, vr_z_floor=1.645)
    _assert(m["momentum"] is True, "VR>1 with significant z must flag momentum")


def test_parse_momentum_negative_vr_below_one():
    ga = "regime=chop (want trend-up), VR4=0.78 (z=-2.01)"
    m = sc._parse_momentum(ga, vr_z_floor=1.645)
    _assert(m["vr"] == 0.78 and m["vr_z"] == -2.01, f"parsed {m}")
    _assert(m["momentum"] is False, "VR<1 is mean-reversion, never momentum")


def test_parse_momentum_handles_missing_fields():
    m = sc._parse_momentum("insufficient bars for a decision", vr_z_floor=1.645)
    _assert(m["vr"] is None and m["vr_z"] is None, "missing VR stays None")
    _assert(m["momentum"] is False, "no VR -> no momentum claim")


def test_mom_cell_shows_full_z():
    cell = sc._mom_cell({"vr": 1.06, "vr_z": 0.59, "momentum": False})
    _assert("z=+0.59" in cell, f"z must not be truncated: {cell!r}")
    edge = sc._mom_cell({"vr": 1.20, "vr_z": 2.00, "momentum": True})
    _assert("MOM^" in edge, f"momentum edge must be flagged: {edge!r}")
    none = sc._mom_cell({"vr": None})
    _assert(none.strip() == "·", f"no-VR cell is a dot: {none!r}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")
