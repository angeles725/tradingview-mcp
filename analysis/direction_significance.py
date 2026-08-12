#!/usr/bin/env python3
"""
Significance test for the directional bias: is there SKILL over the base rate?

Accuracy alone lies when a class dominates (gold went up 59% of months, so
"always up" scores 59% with zero skill). This tool measures the honest quantity
    skill = hit_rate - benchmark
where benchmark = the accuracy of the best CONSTANT predictor (always the
majority realized class). It then asks whether that skill is real with two
independent nulls:

  1. CLUSTER BOOTSTRAP by symbol — resample the symbols with replacement (they
     share a macro regime, so per-window resampling would understate the true
     variance). Gives a 95% CI on skill. If the CI includes 0, there is no
     demonstrated skill.
  2. PERMUTATION — shuffle the predicted directions against the realized moves,
     preserving the up/down mix. p = P(random pairing >= observed accuracy). A
     high p means the specific bias->outcome pairing beats nothing.

Optionally restrict to confidence >= threshold to test whether the HIGH-
confidence calls (where the isotonic map claimed ~75%) carry skill the whole
population does not.

Usage (scipy venv):
    python analysis/direction_significance.py --data corpus/direction-cal-data.jsonl --tf M
    python analysis/direction_significance.py --data ... --tf M --min-conf 0.6
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np


def _benchmark(realized: np.ndarray) -> float:
    """Accuracy of the best constant predictor (always the majority class)."""
    up = float(np.mean(realized > 0))
    return max(up, 1.0 - up)


def _accuracy(pred: np.ndarray, realized: np.ndarray) -> float:
    return float(np.mean(pred == np.sign(realized)))


def skill_test(records: list, min_conf: float | None = None,
               n_boot: int = 5000, seed: int = 7) -> dict:
    recs = [r for r in records if r.get("hit") is not None]
    if min_conf is not None:
        recs = [r for r in recs if r["confidence"] >= min_conf]
    n = len(recs)
    if n < 20:
        return {"n": n, "insufficient": True}

    pred = np.array([1 if r["bias"] == "up" else -1 for r in recs], float)
    realized = np.array([r["realized_dir"] for r in recs], float)
    hit = np.array([r["hit"] for r in recs], float)

    hit_rate = float(hit.mean())
    base_up = float(np.mean(realized > 0))
    benchmark = _benchmark(realized)
    skill = hit_rate - benchmark

    rng = np.random.default_rng(seed)

    # 1) cluster bootstrap by symbol -> CI on skill
    by_sym = defaultdict(list)
    for i, r in enumerate(recs):
        by_sym[r.get("symbol", "?")].append(i)
    groups = [np.array(ix) for ix in by_sym.values()]
    g = len(groups)
    skills = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, g, g)
        idx = np.concatenate([groups[j] for j in pick])
        rz, ht = realized[idx], hit[idx]
        skills[b] = float(ht.mean()) - _benchmark(rz)
    ci = (float(np.percentile(skills, 2.5)), float(np.percentile(skills, 97.5)))

    # 2) permutation: shuffle predictions vs realized (preserve up/down mix)
    accs = np.empty(n_boot)
    rs = np.sign(realized)
    for b in range(n_boot):
        accs[b] = float(np.mean(rng.permutation(pred) == rs))
    p_perm = float((np.sum(accs >= hit_rate) + 1) / (n_boot + 1))

    real_skill = ci[0] > 0 and p_perm < 0.05
    return {
        "n": n, "n_up": int(np.sum(pred > 0)), "n_down": int(np.sum(pred < 0)),
        "n_symbols": g, "min_conf": min_conf,
        "hit_rate": round(hit_rate, 4), "base_up": round(base_up, 4),
        "benchmark": round(benchmark, 4), "skill": round(skill, 4),
        "skill_ci95": [round(ci[0], 4), round(ci[1], 4)],
        "p_permutation": round(p_perm, 4),
        "real_skill": bool(real_skill),
    }


def _fmt(tf: str, res: dict, tag: str = "") -> str:
    if res.get("insufficient"):
        return f"  {tf}{tag}: n={res['n']} — muestra insuficiente (<20)"
    verdict = ("SKILL REAL (CI>0 y p<0.05)" if res["real_skill"]
               else "SIN SKILL demostrable")
    lo, hi = res["skill_ci95"]
    return (f"  {tf}{tag}: n={res['n']} ({res['n_up']}up/{res['n_down']}dn, "
            f"{res['n_symbols']} simbolos)\n"
            f"    hit={res['hit_rate']:.1%}  benchmark(siempre-mayoria)={res['benchmark']:.1%}  "
            f"-> SKILL={res['skill']:+.1%}\n"
            f"    skill CI95=[{lo:+.1%}, {hi:+.1%}]  perm p={res['p_permutation']:.3f}  => {verdict}")


def main():
    ap = argparse.ArgumentParser(description="Directional skill significance test")
    ap.add_argument("--data", required=True)
    ap.add_argument("--tf", default=None, help="single TF; default = all TFs")
    ap.add_argument("--min-conf", type=float, default=None)
    ap.add_argument("--n-boot", type=int, default=5000)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.data) if l.strip()]
    by_tf = defaultdict(list)
    for r in rows:
        by_tf[str(r.get("tf"))].append(r)
    tfs = [args.tf] if args.tf else sorted(by_tf.keys())

    print("=== TEST DE SIGNIFICANCIA DEL SKILL DIRECCIONAL ===")
    print("  benchmark = mejor predictor CONSTANTE (siempre la clase mayoritaria)")
    for tf in tfs:
        recs = by_tf.get(tf, [])
        res = skill_test(recs, min_conf=None, n_boot=args.n_boot)
        print(_fmt(tf, res))
        # also the high-confidence subset, where the isotonic map claimed an edge
        hi = skill_test(recs, min_conf=(args.min_conf or 0.6), n_boot=args.n_boot)
        if not hi.get("insufficient"):
            print(_fmt(tf, hi, tag=f" [conf>={args.min_conf or 0.6}]"))
    print("  Nota: skill>0 con CI que NO cruza 0 y p<0.05 = edge real sobre base-rate.")


if __name__ == "__main__":
    main()
