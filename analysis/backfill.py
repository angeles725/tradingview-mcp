#!/usr/bin/env python3
"""
Backfill forecast calibration over accumulated history.

Walk NON-OVERLAPPING windows through the stored bars; at each window end t build
the SAME zero-drift cones analyze.py uses — from bars[:t] ONLY (no lookahead) —
and score them against the realized close at t+horizon (already known in history).
This produces an INDEPENDENT calibration sample immediately, instead of waiting
for live forecasts to mature. Writes to a separate log so it never mixes with the
live record.

Usage (scipy venv):
    python analysis/collect.py --symbol OANDA:XAUUSD --tf 15 --emit \
      | python analysis/backfill.py --symbol XAUUSD --tf 15 --horizon 4 --reset
    python analysis/forecast.py stats --log corpus/forecasts-backfill.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

import quant as q
import forecast as fc

DEFAULT_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "corpus", "forecasts-backfill.jsonl")
_QK = ("P5", "P25", "P50", "P75", "P95", "p_up", "model")


def _cones(S0, ret, horizon, seed=7):
    """The zero-drift forecast cones, exactly as analyze.py builds them."""
    vg = q.garch11_vol(ret)
    sigma = vg[0] if vg else q.ewma_vol(ret)
    return {
        "gaussian": q.mc_gaussian(S0, sigma, horizon, 0.0, seed=seed),
        "bootstrap": q.mc_bootstrap(S0, ret, horizon, seed=seed),
        "student_t": q.mc_student_t(S0, ret, horizon, seed=seed),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--horizon", type=int, default=4)
    ap.add_argument("--warmup", type=int, default=60)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--reset", action="store_true", help="truncate the log first")
    args = ap.parse_args()

    payload = json.load(sys.stdin)
    bars = payload.get("bars") or payload.get("ohlcv") or []
    if len(bars) < args.warmup + args.horizon + 1:
        raise SystemExit(f"need >= {args.warmup + args.horizon + 1} bars, got {len(bars)}")
    c = np.array([b["close"] for b in bars], float)
    t_ = np.array([b.get("time", i) for i, b in enumerate(bars)], float)
    n, h = c.size, args.horizon
    dt = np.diff(t_); step_sec = int(np.median(dt[dt > 0])) if np.any(dt > 0) else 0

    if args.reset and os.path.exists(args.log):
        os.remove(args.log)

    made = 0
    for t in range(args.warmup, n - h, h):        # step = horizon -> non-overlapping
        cs, ts = c[:t + 1], t_[:t + 1]
        ret = q.log_returns(cs, times=ts)         # gap-aware, bars[:t] only
        if ret.size < 30:
            continue
        S0 = float(c[t])
        cn = _cones(S0, ret, h)
        rec = {
            "symbol": args.symbol, "tf": args.tf, "horizon_bars": h,
            "bar_step_sec": step_sec, "made_at_unix": int(t_[t]),
            "target_unix": int(t_[t + h]), "S0": S0,
            "cross_gap_dropped": int((cs.size - 1) - ret.size),
            "cones": {m: {k: cn[m][k] for k in _QK} for m in cn},
            "realized": None,
        }
        fc.append_log(args.log, fc.score_record(rec, float(c[t + h])))
        made += 1

    print(f"backfilled {made} non-overlapping forecasts (h={h}) -> {args.log}")


if __name__ == "__main__":
    main()
