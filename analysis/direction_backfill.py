#!/usr/bin/env python3
"""
Directional-bias CALIBRATION via walk-forward over history.

direction.py assigns a confidence to each up/down lean, but that confidence
starts as a HAND-CHOSEN prior (TF_RELIABILITY) — a hypothesis, not evidence.
This tool tests the hypothesis: walk NON-OVERLAPPING windows through stored/
historical bars, at each window end compute the bias from bars[:t] ONLY (no
lookahead), then check the REALIZED direction over the next `horizon` bars
(already known in history). Aggregating hits vs confidence yields a reliability
diagram: does "conf 0.7" actually win ~70% of the time? Is there ANY edge over a
coin flip, per timeframe?

This mirrors backfill.py (the cone calibrator) so the two share the same
leakage-free, non-overlapping, gap-aware discipline. The honest expected result
intraday is ~50% (no edge) — this tool is what would PROVE it, or prove the
higher timeframes carry a real trend-persistence edge.

Usage (scipy venv):
    # from the 15m persistent store:
    python analysis/direction_backfill.py --store analysis/data --symbol OANDA:XAUUSD --tf 15
    # from a live pull (any TF) on stdin:
    node src/cli/index.js ohlcv --count 500 --expect-symbol OANDA:XAUUSD \
      | python analysis/direction_backfill.py --symbol OANDA:XAUUSD --tf D
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

import direction as direc

# Default directional horizon per timeframe, in bars — how far ahead the lean is
# checked. Mirrors the cone horizons (analyze/backfill use ~4-5 bars).
TF_HORIZON = {"1": 4, "5": 4, "15": 4, "30": 4, "60": 4, "120": 3, "240": 3,
              "D": 5, "1D": 5, "W": 4, "1W": 4, "M": 3, "1M": 3}


def _realized_dir(c: np.ndarray, t: int, h: int) -> int:
    """Sign of the net move over the next h bars: +1 up, -1 down, 0 unchanged."""
    d = c[t + h] - c[t]
    return 1 if d > 0 else -1 if d < 0 else 0


def walk_forward(bars: list, symbol: str, tf: str, horizon: int,
                 warmup: int) -> list:
    """Non-overlapping walk-forward. At each window end t compute the bias from
    bars[:t+1] and pair it with the realized direction at t+h. Returns a list of
    scored prediction records (no lookahead — bias sees only bars[:t+1])."""
    o = np.array([b.get("open", b["close"]) for b in bars], float)
    hi = np.array([b.get("high", b["close"]) for b in bars], float)
    lo = np.array([b.get("low", b["close"]) for b in bars], float)
    c = np.array([b["close"] for b in bars], float)
    v = np.array([b.get("volume", 0.0) for b in bars], float)
    t_ = np.array([b.get("time", i) for i, b in enumerate(bars)], float)
    n, h = c.size, horizon
    out = []
    for t in range(warmup, n - h, h):                 # step = horizon -> independent
        try:
            rec = direc.bias_from_bars(o[:t + 1], hi[:t + 1], lo[:t + 1],
                                       c[:t + 1], v[:t + 1], t_[:t + 1], tf)
        except ValueError:
            continue
        rd = _realized_dir(c, t, h)
        hit = None
        if rec["bias"] in ("up", "down"):
            pred = 1 if rec["bias"] == "up" else -1
            hit = 1 if pred == rd else 0
        out.append({
            "symbol": symbol, "tf": tf, "horizon_bars": h,
            "made_at_unix": int(t_[t]), "target_unix": int(t_[t + h]),
            "bias": rec["bias"], "confidence": rec["confidence"],
            "realized_dir": rd, "hit": hit,
        })
    return out


def calibrate(records: list) -> dict:
    """Reliability report over scored prediction records.

    - hit_rate: accuracy of DIRECTIONAL (non-flat) calls; the honest benchmark is
      0.50 (a coin flip on direction).
    - buckets: hit-rate per confidence bin — the reliability diagram. If accuracy
      does NOT rise with confidence, the confidence carries no information.
    - brier: mean((confidence - hit)^2) treating confidence as p(correct);
      compare to 0.25, the Brier score of always saying p=0.5.
    - base_rate_up: fraction of ALL windows that went up (momentum can skew it).
    """
    directional = [r for r in records if r.get("hit") is not None]
    n_dir = len(directional)
    n_flat = sum(1 for r in records if r.get("bias") == "flat")
    hit_rate = float(np.mean([r["hit"] for r in directional])) if n_dir else float("nan")
    base_up = (float(np.mean([1 if r["realized_dir"] > 0 else 0 for r in records]))
               if records else float("nan"))
    brier = (float(np.mean([(r["confidence"] - r["hit"]) ** 2 for r in directional]))
             if n_dir else float("nan"))

    edges = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    buckets = []
    for lo, hi in edges:
        b = [r for r in directional if lo <= r["confidence"] < hi]
        buckets.append({
            "lo": lo, "hi": min(hi, 1.0), "n": len(b),
            "hit_rate": float(np.mean([r["hit"] for r in b])) if b else None,
            "mean_conf": float(np.mean([r["confidence"] for r in b])) if b else None,
        })

    up = [r for r in directional if r["bias"] == "up"]
    dn = [r for r in directional if r["bias"] == "down"]
    return {
        "n_total": len(records), "n_directional": n_dir, "n_flat": n_flat,
        "hit_rate": hit_rate, "base_rate_up": base_up, "brier": brier,
        "hit_rate_up": float(np.mean([r["hit"] for r in up])) if up else None,
        "hit_rate_down": float(np.mean([r["hit"] for r in dn])) if dn else None,
        "n_up": len(up), "n_down": len(dn),
        "buckets": buckets,
    }


def _fmt(cal: dict, symbol: str, tf: str) -> str:
    o = []
    o.append(f"--- {symbol} {tf}: n={cal['n_total']} "
             f"(dir={cal['n_directional']}, flat={cal['n_flat']}) ---")
    hr = cal["hit_rate"]
    if hr == hr and cal["n_directional"] > 0:
        edge = hr - 0.5
        verdict = ("SIN EDGE (~coin flip)" if abs(edge) < 0.05
                   else "edge" + (" alcista" if edge > 0 else " (contrario!)"))
        o.append(f"  hit-rate direccional: {hr:.1%}  (benchmark 50% | {verdict})")
        o.append(f"  up {cal['hit_rate_up'] or float('nan'):.1%} (n={cal['n_up']}) | "
                 f"down {cal['hit_rate_down'] or float('nan'):.1%} (n={cal['n_down']}) | "
                 f"base-rate up {cal['base_rate_up']:.1%}")
        o.append(f"  Brier {cal['brier']:.3f}  (0.25 = confianza sin informacion)")
        o.append("  reliability (conf -> acierto real):")
        for b in cal["buckets"]:
            if b["n"] == 0:
                continue
            o.append(f"    conf {b['lo']:.1f}-{b['hi']:.1f}: {b['hit_rate']:.1%} "
                     f"acierto  (n={b['n']}, conf med {b['mean_conf']:.2f})")
    else:
        o.append("  (sin llamadas direccionales — todo plano; nada que calibrar)")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser(description="Directional-bias calibration (walk-forward)")
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--horizon", type=int, default=None, help="bars ahead; default per-TF")
    ap.add_argument("--warmup", type=int, default=60)
    ap.add_argument("--store", default=None, help="backfill from collect.py store dir")
    ap.add_argument("--log", default=None, help="also append scored records here (JSONL)")
    ap.add_argument("--json", action="store_true", help="emit the calibration dict as JSON")
    args = ap.parse_args()

    horizon = args.horizon if args.horizon is not None else TF_HORIZON.get(str(args.tf), 4)

    if args.store:
        import collect
        rows = list(collect.load_store(collect.store_path(args.store, args.symbol, args.tf)).values())
        rows.sort(key=lambda r: r["time"])
        bars = rows
    else:
        payload = json.load(sys.stdin)
        bars = payload.get("bars") or payload.get("ohlcv") or []

    if len(bars) < args.warmup + horizon + 1:
        raise SystemExit(f"need >= {args.warmup + horizon + 1} bars, got {len(bars)}")

    records = walk_forward(bars, args.symbol, str(args.tf), horizon, args.warmup)
    if args.log:
        with open(args.log, "a") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
    cal = calibrate(records)
    if args.json:
        cal["symbol"] = args.symbol
        cal["tf"] = str(args.tf)
        cal["horizon"] = horizon
        print(json.dumps(cal))
    else:
        print(_fmt(cal, args.symbol, str(args.tf)))


if __name__ == "__main__":
    main()
