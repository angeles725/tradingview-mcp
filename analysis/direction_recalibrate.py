#!/usr/bin/env python3
"""
Recalibrate the directional confidence from walk-forward calibration data.

direction.py's raw confidence is a hand-chosen heuristic; direction_backfill.py
showed it is often uninformative (Brier > 0.25) or even inverted. This tool
replaces the guess with an EMPIRICAL map raw_confidence -> P(call is correct),
fit PER TIMEFRAME from pooled multi-symbol history, and — crucially — validated
OUT OF SAMPLE. For each TF it compares three candidates on a held-out time split:

  1. raw       : trust the raw confidence as-is (p = confidence)
  2. marginal  : ignore the score, output the base rate of correctness (p = mean hit)
  3. isotonic  : a monotonic map fit on the training split

and adopts the one with the LOWEST out-of-sample Brier. This can never ship
something worse than honestly collapsing to the base rate: if the score carries
no information, 'marginal' wins and the confidence flattens to reality.

The fitted map is stored as plain (x, y) arrays so direction.py applies it with
numpy.interp at inference — no sklearn dependency at runtime.

Usage (scipy venv):
    python analysis/direction_recalibrate.py --data corpus/direction-cal-data.jsonl \
      --out corpus/direction-calibration.json
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

import numpy as np

MIN_N = 40          # below this a TF is left uncalibrated (too little evidence)
TRAIN_FRAC = 0.7    # time-ordered split for out-of-sample validation


def _brier(p, y):
    p = np.clip(np.asarray(p, float), 0.0, 1.0)
    y = np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def _fit_isotonic(x_train, y_train):
    """Return (xs, ys) of a monotonic non-decreasing fit, or None if unavailable."""
    try:
        from sklearn.isotonic import IsotonicRegression
    except Exception:
        return None
    ir = IsotonicRegression(out_of_bounds="clip", increasing=True, y_min=0.0, y_max=1.0)
    ir.fit(x_train, y_train)
    xs = np.linspace(float(np.min(x_train)), float(np.max(x_train)), 21)
    ys = ir.predict(xs)
    return xs.tolist(), ys.tolist()


def recalibrate_tf(records: list) -> dict:
    """Fit and OOS-validate the three candidates for ONE timeframe's directional
    records (each has confidence, hit, made_at_unix). Returns the adopted map."""
    recs = sorted([r for r in records if r.get("hit") is not None],
                  key=lambda r: r.get("made_at_unix", 0))
    n = len(recs)
    conf = np.array([r["confidence"] for r in recs], float)
    hit = np.array([r["hit"] for r in recs], float)
    n_up = sum(1 for r in recs if r["bias"] == "up")
    n_down = sum(1 for r in recs if r["bias"] == "down")

    if n < MIN_N:
        return {"method": "none", "n": n, "n_up": n_up, "n_down": n_down,
                "adopted": False, "reason": f"n<{MIN_N}, insufficient evidence",
                "marginal": round(float(hit.mean()), 4) if n else None}

    cut = int(n * TRAIN_FRAC)
    xtr, ytr = conf[:cut], hit[:cut]
    xte, yte = conf[cut:], hit[cut:]
    if xte.size < 5 or ytr.size < 5:
        return {"method": "none", "n": n, "adopted": False,
                "reason": "split too small", "marginal": round(float(hit.mean()), 4)}

    marg = float(ytr.mean())
    candidates = {
        "raw": _brier(xte, yte),
        "marginal": _brier(np.full(xte.size, marg), yte),
    }
    iso = _fit_isotonic(xtr, ytr)
    if iso is not None:
        xs, ys = iso
        candidates["isotonic"] = _brier(np.interp(xte, xs, ys), yte)

    winner = min(candidates, key=candidates.get)
    out = {
        "n": n, "n_up": n_up, "n_down": n_down,
        "brier_raw": round(candidates["raw"], 4),
        "brier_marginal": round(candidates["marginal"], 4),
        "brier_isotonic": round(candidates.get("isotonic", float("nan")), 4)
                          if "isotonic" in candidates else None,
        "hit_rate": round(float(hit.mean()), 4),
        "method": winner,
        "adopted": winner != "raw",
    }
    if winner == "isotonic":
        out["x"], out["y"] = xs, ys
    elif winner == "marginal":
        out["value"] = round(marg, 4)
    else:  # raw wins — the heuristic was already best; nothing to override
        out["reason"] = "raw confidence already best OOS"
    return out


def build_map(records: list) -> dict:
    by_tf = defaultdict(list)
    for r in records:
        by_tf[str(r.get("tf"))].append(r)
    return {tf: recalibrate_tf(rs) for tf, rs in sorted(by_tf.items())}


def apply_calibration(raw_conf: float, tf: str, calmap: dict) -> float:
    """Map a raw confidence to the calibrated P(correct) for a TF. Falls back to
    the raw value when the TF has no adopted map (kept honest by direction.py,
    which flags an uncalibrated TF)."""
    m = (calmap or {}).get(str(tf))
    if not m or not m.get("adopted"):
        return float(raw_conf)
    if m["method"] == "isotonic":
        return float(np.interp(raw_conf, m["x"], m["y"]))
    if m["method"] == "marginal":
        return float(m["value"])
    return float(raw_conf)


def _fmt(calmap: dict) -> str:
    o = ["=== RECALIBRACION DE CONFIANZA (OOS, por TF) ==="]
    for tf, m in calmap.items():
        if m["method"] == "none":
            o.append(f"  {tf:<4} n={m['n']:<4} -> SIN CALIBRAR ({m.get('reason')})")
            continue
        tag = {"raw": "cruda (ya era mejor)", "marginal": "MARGINAL (colapsa a base-rate)",
               "isotonic": "ISOTONICA"}[m["method"]]
        extra = f"val={m['value']}" if m["method"] == "marginal" else ""
        o.append(f"  {tf:<4} n={m['n']:<4} up/dn={m['n_up']}/{m['n_down']} "
                 f"hit={m['hit_rate']:.1%} | Brier raw={m['brier_raw']} "
                 f"marg={m['brier_marginal']} iso={m['brier_isotonic']} "
                 f"-> {tag} {extra}")
    o.append("  Nota: 'marginal' = la confianza cruda no aportaba; la honesta es la base-rate.")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser(description="Recalibrate directional confidence (OOS)")
    ap.add_argument("--data", required=True, help="pooled walk-forward JSONL")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "corpus",
        "direction-calibration.json"))
    args = ap.parse_args()

    records = [json.loads(l) for l in open(args.data) if l.strip()]
    calmap = build_map(records)
    calmap["_note"] = ("raw_confidence -> P(correct) per TF, OOS-validated; "
                       "method=marginal means the raw score was uninformative.")
    with open(args.out, "w") as f:
        json.dump(calmap, f, indent=2)
    print(_fmt({k: v for k, v in calmap.items() if k != "_note"}))
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
