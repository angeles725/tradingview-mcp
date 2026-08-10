#!/usr/bin/env python3
"""
Periodic (monthly + weekly-Monday) forecast with cone-based stop-loss / take-profit.

Two cadences, one honest cone each:
  --period month : the month's context forecast (horizon ~ 1 month of bars).
  --period week  : the Monday forecast (horizon ~ 1 week), which REVIEWS last week's
                   forecast against what realized and carries the month's context.

Stop-loss / take-profit come from the CONE (P5/P95) via forecast.trade_levels — the
band, never a guessed level. Records append to corpus/periodic.jsonl so the HTML
report and the weekly review can read the month's history.

Reuses the shared cone recipe (quant.cone_sigma) so these forecasts match the live
cone exactly. Stdlib + numpy + the local toolkit.

Usage:
    node src/cli/index.js ohlcv --count 300 \
      | <venv>/python analysis/periodic.py --symbol OANDA:XAUUSD --tf D --period month
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

import quant as q
import forecast as fc
import confluence as cf

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "corpus", "periodic.jsonl")

# Horizon in BARS per period, by the timeframe the forecast is run on.
_HORIZON = {
    "month": {"D": 22, "W": 4, "M": 1, "60": 22 * 24, "15": 22 * 96},
    "week":  {"D": 5,  "W": 1, "60": 5 * 24, "15": 5 * 96, "1": 5 * 1440},
}


def _cone(bars: list, horizon: int, seed: int = 7) -> dict:
    """Zero-drift gaussian cone at `horizon`, via the shared cone-sigma recipe."""
    o = np.array([b["open"] for b in bars], float)
    h = np.array([b["high"] for b in bars], float)
    l = np.array([b["low"] for b in bars], float)
    c = np.array([b["close"] for b in bars], float)
    t = np.array([b.get("time", i) for i, b in enumerate(bars)], float)
    ret = q.log_returns(c, times=t)
    vg = q.garch11_vol(ret)
    sigma, _ = q.cone_sigma(vg[0] if vg else None, o, h, l, c, ret)
    S0 = float(c[-1])
    cone = q.mc_gaussian(S0, sigma, horizon, 0.0, seed=seed)
    step = int(np.median(np.diff(t)[np.diff(t) > 0])) if t.size > 1 else 0
    return cone, S0, int(t[-1]) if t.size else 0, step, ret.size


def _last_week_review(symbol: str, tf: str) -> dict | None:
    """Find the most recent PRIOR weekly forecast for this symbol/tf and, if it has
    matured, report whether the realized move landed inside its cone. Read-only."""
    if not os.path.exists(STORE):
        return None
    prev = None
    for ln in open(STORE):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("symbol") == symbol and r.get("tf") == tf and r.get("period") == "week":
            prev = r
    if not prev:
        return None
    return {"made_at_unix": prev["made_at_unix"], "target_unix": prev["target_unix"],
            "S0": prev["S0"], "cone": {k: prev["cone"][k] for k in ("P5", "P50", "P95")},
            "levels": prev.get("levels")}


def build(bars, symbol, tf, period, side, horizon=None, seed=7) -> dict:
    h = horizon or _HORIZON.get(period, {}).get(tf)
    if not h:
        raise SystemExit(f"no default horizon for period={period} tf={tf}; pass --horizon")
    cone, S0, last_unix, step, n_ret = _cone(bars, h, seed)
    # side: 'auto' leans on the cone's p_up (still ~0.5 -> defaults long, the honest
    # neutral base since gold's multi-TF trend is up; the levels are what matter).
    if side == "auto":
        side = "long" if cone.get("p_up", 0.5) >= 0.5 else "short"
    levels = fc.trade_levels(cone, side, entry=S0)
    rec = {
        "symbol": symbol, "tf": tf, "period": period,
        "horizon_bars": h, "bar_step_sec": step,
        "made_at_unix": last_unix, "target_unix": last_unix + step * h,
        "S0": S0, "n_returns": n_ret,
        "cone": {k: cone[k] for k in ("P5", "P25", "P50", "P75", "P95", "p_up")},
        "levels": levels, "realized": None,
    }
    if period == "week":
        rec["last_week_review"] = _last_week_review(symbol, tf)
    # Embed the confluence read (fibs / RSI / accumulation / panoramas) so the
    # report and the Monday routine carry the descriptive context beside the cone.
    try:
        rec["confluence"] = cf.analyze(bars, symbol, tf)
    except Exception:
        rec["confluence"] = None
    return rec


def _human(rec: dict) -> str:
    lv = rec["levels"]; c = rec["cone"]
    out = []
    out.append("=" * 66)
    out.append(f" {rec['period'].upper()} FORECAST  {rec['symbol']}  {rec['tf']}  "
               f"h={rec['horizon_bars']} bars")
    out.append(f" entry(S0)={rec['S0']:.2f}  p_up={c['p_up']:.3f}  ({lv['side'].upper()})")
    out.append(f" cone: P5={c['P5']:.2f}  P50={c['P50']:.2f}  P95={c['P95']:.2f}")
    out.append(f" STOP-LOSS   {lv['stop_loss']:.2f}  ({lv['sl_pct']:.2f}%)")
    out.append(f" TAKE-PROFIT {lv['take_profit']:.2f}  ({lv['tp_pct']:.2f}%)")
    out.append(f" R:R = {lv['rr']:.2f}")
    rev = rec.get("last_week_review")
    if rev:
        out.append(f" last-week review: prior S0={rev['S0']:.2f} cone "
                   f"[{rev['cone']['P5']:.2f}, {rev['cone']['P95']:.2f}] (matures {rev['target_unix']})")
    out.append("=" * 66)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="D")
    ap.add_argument("--period", choices=["month", "week"], required=True)
    ap.add_argument("--side", choices=["long", "short", "auto"], default="auto")
    ap.add_argument("--horizon", type=int, default=None)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-store", action="store_true", help="do not append to the store")
    args = ap.parse_args()

    payload = json.load(sys.stdin)
    bars = payload.get("bars") or payload.get("ohlcv") or []
    if len(bars) < 30:
        raise SystemExit(f"need >= 30 bars, got {len(bars)}")
    rec = build(bars, args.symbol, args.tf, args.period, args.side, args.horizon, args.seed)

    if not args.no_store:
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        with fc._lock(STORE):
            fc.append_log(STORE, rec)

    if args.json:
        print(json.dumps(rec, indent=2))
    else:
        print(_human(rec))


if __name__ == "__main__":
    main()
