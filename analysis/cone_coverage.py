#!/usr/bin/env python3
"""
Cone COVERAGE flag — mark each (symbol, timeframe) cone reliable / too-tight /
too-wide, so a live cone can warn when THIS instrument's band lies.

The cones are the trustworthy half of the toolkit (backfill showed ~88-90%
aggregate coverage of the 90% band), but that aggregate hides real per-symbol
outliers: gold's DAILY 90% band only covered 79% — a stop sized off it is
breached ~21% of the time, not 10%. The honest fix is NOT a conformal delta
(validated OOS as overfit at these sample sizes) but a FLAG: measure realized
coverage per symbol|tf and stamp a verdict the cone can display.

verdict:
  reliable      |cover_90 - 0.90| <= 0.05  (band delivers roughly what it says)
  too-tight     cover_90 < 0.85            (DANGER: stops breach more than nominal)
  too-wide      cover_90 > 0.95            (over-conservative; safe but wastes room)
  insufficient  n < MIN_N                  (not enough history to judge)

Usage (scipy venv):
    python analysis/cone_coverage.py --log corpus/forecasts-backfill-cone.jsonl \
      --out corpus/cone-coverage.json
"""
from __future__ import annotations

import argparse
import json
import os

import forecast as fc

MIN_N = 30
REF_MODEL = "gaussian"     # the primary cone model the verdict keys on
DEFAULT_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "corpus", "cone-coverage.json")


def load_map(path: str = DEFAULT_MAP) -> dict:
    """Load the coverage flag map (absent => empty => no warnings shown)."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _verdict(cover_90: float, n: int) -> str:
    if n < MIN_N:
        return "insufficient"
    if cover_90 < 0.85:
        return "too-tight"
    if cover_90 > 0.95:
        return "too-wide"
    return "reliable"


def build_coverage_map(records: list) -> dict:
    """Per 'symbol|tf' coverage + verdict, from scored cone backfill records."""
    groups: dict = {}
    for r in records:
        if not r.get("realized"):
            continue
        groups.setdefault(f"{r.get('symbol')}|{r.get('tf')}", []).append(r)
    out = {}
    for key, recs in groups.items():
        cal = fc.calibration(recs)
        models = cal.get("models") or {}
        m = models.get(REF_MODEL) or (next(iter(models.values())) if models else None)
        if not m:                       # too few independent forecasts to score a band
            out[key] = {"cover_90": None, "cover_50": None,
                        "n": len(recs), "verdict": "insufficient"}
            continue
        c90, c50, n = m["cover_90"], m["cover_50"], m["n"]
        out[key] = {"cover_90": round(c90, 3), "cover_50": round(c50, 3),
                    "n": n, "verdict": _verdict(c90, n)}
    return out


DEFAULT_SCALAR_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "corpus", "cone-coverage-scalar.json")


def load_scalar_map(path: str = DEFAULT_SCALAR_MAP) -> dict:
    """Load the per symbol|tf scalar widening map (absent => empty => no rescale)."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def build_scalar_map(records: list, min_n: int = 20) -> dict:
    """Per 'symbol|tf' single-scalar widening factor k (fit on REF_MODEL's 90%
    band), from scored cone backfill records. Groups below `min_n` are omitted so
    a thin tail can never mint a factor. Mirrors build_coverage_map's grouping."""
    records = fc._dedupe(records)
    groups: dict = {}
    for r in records:
        if not r.get("realized"):
            continue
        groups.setdefault(f"{r.get('symbol')}|{r.get('tf')}", []).append(r)
    out = {}
    for key, recs in groups.items():
        k = fc.coverage_scalar_fit(recs, REF_MODEL, "90", min_n=min_n)
        if k is None:
            continue
        n = sum(1 for r in recs if r.get("realized") and REF_MODEL in r.get("cones", {}))
        out[key] = {"k": round(k, 4), "n": n}
    return out


def coverage_verdict(symbol: str, tf: str, cmap: dict) -> dict | None:
    """Look up the verdict for a live cone. None if unknown (no warning shown)."""
    return (cmap or {}).get(f"{symbol}|{tf}")


def warning_line(symbol: str, tf: str, cmap: dict) -> str:
    """One-line cone warning for analyze.py, empty when reliable/unknown."""
    v = coverage_verdict(symbol, tf, cmap)
    if not v or v["verdict"] in ("reliable", "insufficient"):
        return ""
    if v["verdict"] == "too-tight":
        return (f"  [!] COBERTURA: el cono 90% de {symbol} {tf} SOLO cubrio "
                f"{v['cover_90']:.0%} historicamente (n={v['n']}) -> BANDA ESTRECHA, "
                f"un stop en P5/P95 se rompe mas de lo nominal. Dale mas margen.")
    return (f"  [i] COBERTURA: el cono 90% de {symbol} {tf} cubrio {v['cover_90']:.0%} "
            f"(n={v['n']}) -> banda ANCHA (conservadora).")


def main():
    ap = argparse.ArgumentParser(description="Cone coverage flag builder")
    ap.add_argument("--log", required=True, help="scored cone backfill JSONL")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "corpus", "cone-coverage.json"))
    args = ap.parse_args()

    records = fc.read_log(args.log)
    cmap = build_coverage_map(records)
    with open(args.out, "w") as f:
        json.dump({**cmap, "_note": "per symbol|tf cone coverage of the 90% band; "
                   "verdict flags too-tight/too-wide/reliable for stop sizing."},
                  f, indent=2)

    order = {"too-tight": 0, "too-wide": 1, "reliable": 2, "insufficient": 3}
    rows = sorted(cmap.items(), key=lambda kv: (order[kv[1]["verdict"]], kv[0]))
    print("=== COBERTURA DE CONOS por simbolo|tf (banda 90% debe ~0.90) ===")
    print(f"  {'symbol|tf':<26}{'cover90':>9}{'cover50':>9}{'n':>6}  verdict")
    for key, v in rows:
        print(f"  {key:<26}{v['cover_90']:>9.2f}{v['cover_50']:>9.2f}{v['n']:>6}  {v['verdict']}")
    n_tight = sum(1 for _, v in rows if v["verdict"] == "too-tight")
    print(f"\n  {n_tight} cono(s) DEMASIADO ESTRECHOS (riesgo real de sizing) -> {args.out}")


if __name__ == "__main__":
    main()
