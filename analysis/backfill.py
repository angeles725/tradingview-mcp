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


def backfill_bars(bars: list, symbol: str, tf: str, horizon: int,
                  warmup: int, log: str) -> int:
    """Walk NON-OVERLAPPING windows over `bars`, build gap-aware zero-drift cones
    from bars[:t] only, score each against the realized close at t+horizon, and
    append the scored record to `log`. Returns the number of forecasts made."""
    if len(bars) < warmup + horizon + 1:
        return 0
    c = np.array([b["close"] for b in bars], float)
    t_ = np.array([b.get("time", i) for i, b in enumerate(bars)], float)
    n, h = c.size, horizon
    dt = np.diff(t_); step_sec = int(np.median(dt[dt > 0])) if np.any(dt > 0) else 0
    made = 0
    for t in range(warmup, n - h, h):             # step = horizon -> non-overlapping
        cs, ts = c[:t + 1], t_[:t + 1]
        ret = q.log_returns(cs, times=ts)         # gap-aware, bars[:t] only
        if ret.size < 30:
            continue
        S0 = float(c[t])
        cn = _cones(S0, ret, h)
        rec = {
            "symbol": symbol, "tf": tf, "horizon_bars": h,
            "bar_step_sec": step_sec, "made_at_unix": int(t_[t]),
            "target_unix": int(t_[t + h]), "S0": S0,
            "cross_gap_dropped": int((cs.size - 1) - ret.size),
            "cones": {m: {k: cn[m][k] for k in _QK} for m in cn},
            "realized": None,
        }
        fc.append_log(log, fc.score_record(rec, float(c[t + h])))
        made += 1
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--horizon", type=int, default=4)
    ap.add_argument("--warmup", type=int, default=60)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--reset", action="store_true", help="truncate the log first")
    ap.add_argument("--store", default=None,
                    help="backfill from collect.py's persistent store dir instead of stdin")
    ap.add_argument("--symbols", default=None,
                    help="with --store: comma-separated symbols to backfill in one pass")
    args = ap.parse_args()

    if args.reset and os.path.exists(args.log):
        os.remove(args.log)

    if args.store:
        import collect
        symbols = [s.strip() for s in (args.symbols or args.symbol).split(",") if s.strip()]
        total = 0
        for sym in symbols:
            rows = list(collect.load_store(collect.store_path(args.store, sym, args.tf)).values())
            rows.sort(key=lambda r: r["time"])
            made = backfill_bars(rows, sym, args.tf, args.horizon, args.warmup, args.log)
            total += made
            print(f"  {sym:<18} {made:>4} forecasts (h={args.horizon}, {len(rows)} bars)")
        print(f"backfilled {total} non-overlapping forecasts across "
              f"{len(symbols)} symbol(s) -> {args.log}")
        return

    payload = json.load(sys.stdin)
    bars = payload.get("bars") or payload.get("ohlcv") or []
    if len(bars) < args.warmup + args.horizon + 1:
        raise SystemExit(f"need >= {args.warmup + args.horizon + 1} bars, got {len(bars)}")
    made = backfill_bars(bars, args.symbol, args.tf, args.horizon, args.warmup, args.log)
    print(f"backfilled {made} non-overlapping forecasts (h={args.horizon}) -> {args.log}")


if __name__ == "__main__":
    main()
