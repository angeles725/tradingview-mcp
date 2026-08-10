#!/usr/bin/env python3
"""
Confluence analysis: combine Fibonacci (up + down), RSI, EMA-trend, accumulation
(OBV + volume-profile POC), and candle balance into ONE read with bull / base /
bear scenarios. Descriptive, not predictive — it maps where levels stack up so the
cone can be read against them.

Usage:
    node src/cli/index.js ohlcv --count 300 \
      | <venv>/python analysis/confluence.py --symbol OANDA:XAUUSD --tf D
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

import quant as q

_KEY = (0.382, 0.5, 0.618, 0.786)      # the fib levels traders actually watch


def analyze(bars: list, symbol: str, tf: str) -> dict:
    o = np.array([b["open"] for b in bars], float)
    h = np.array([b["high"] for b in bars], float)
    l = np.array([b["low"] for b in bars], float)
    c = np.array([b["close"] for b in bars], float)
    v = np.array([b.get("volume", 0) for b in bars], float)
    price = float(c[-1])

    lo, hi = float(l.min()), float(h.max())
    i_lo, i_hi = int(l.argmin()), int(h.argmax())
    leg = "up" if i_hi > i_lo else "down"          # which extreme came last

    fib_up = q.fib_levels(lo, hi, "up")            # supports on a pullback (bull leg)
    fib_dn = q.fib_levels(lo, hi, "down")          # resistances on a bounce (bear leg)

    rsi = q.rsi_wilder(c, 14)
    rsi_now = float(rsi[~np.isnan(rsi)][-1]) if np.any(~np.isnan(rsi)) else float("nan")
    rsi_state = ("overbought" if rsi_now >= 70 else "oversold" if rsi_now <= 30 else "neutral")

    ob = q.obv(c, v)
    n = min(20, ob.size - 1)
    obv_slope = float(ob[-1] - ob[-1 - n]) if n > 0 else 0.0
    accumulation = "accumulation" if obv_slope > 0 else "distribution" if obv_slope < 0 else "flat"
    poc = q.volume_profile_poc(h, l, v) if v.sum() > 0 else float("nan")

    up_c = int(np.sum(c[-20:] > o[-20:])); dn_c = int(np.sum(c[-20:] < o[-20:]))
    last_bull = bool(c[-1] > o[-1])

    ema_fast = float(q.ema(c, 50)[-1]); ema_slow = float(q.ema(c, 200)[-1]) if c.size >= 200 else float("nan")
    trend = "up" if price > ema_slow else "down" if ema_slow == ema_slow and price < ema_slow else "flat"

    # nearest fib support below / resistance above (from the bull-leg retracement)
    below = sorted([p for p in fib_up.values() if p < price], reverse=True)
    above = sorted([p for p in fib_up.values() if p > price])
    fib_support = below[0] if below else lo
    fib_resistance = above[0] if above else hi

    scenarios = _scenarios(price, fib_support, fib_resistance, poc, rsi_state,
                           accumulation, trend)
    return {
        "symbol": symbol, "tf": tf, "price": price,
        "swing": {"low": lo, "high": hi, "leg": leg},
        "fib_bull": {str(k): round(v_, 2) for k, v_ in fib_up.items() if k in _KEY},
        "fib_bear": {str(k): round(v_, 2) for k, v_ in fib_dn.items() if k in _KEY},
        "rsi": round(rsi_now, 1), "rsi_state": rsi_state,
        "accumulation": accumulation, "obv_slope": round(obv_slope, 0), "poc": round(poc, 2),
        "candles_20": {"bull": up_c, "bear": dn_c, "last": "bull" if last_bull else "bear"},
        "ema50": round(ema_fast, 2), "ema200": round(ema_slow, 2), "trend": trend,
        "nearest": {"fib_support": round(fib_support, 2), "fib_resistance": round(fib_resistance, 2)},
        "scenarios": scenarios,
    }


def _scenarios(price, sup, res, poc, rsi_state, accum, trend) -> dict:
    return {
        "bull": (f"Hold above fib support {sup:.2f}"
                 + (f" and POC {poc:.2f}" if poc == poc else "")
                 + f" -> target resistance {res:.2f}. "
                 + ("Favoured: trend up + accumulation." if trend == "up" and accum == "accumulation"
                    else "Weaker: trend/flow not both up.")),
        "base": (f"Chop between {sup:.2f} and {res:.2f}; "
                 + ("RSI " + rsi_state + " argues for mean-reversion inside the range."
                    if rsi_state != "neutral" else "no edge, wait.")),
        "bear": (f"Lose fib support {sup:.2f} -> next fib/POC below. "
                 + ("Favoured if flow turns to distribution." if accum == "distribution"
                    else "Less likely while accumulation holds.")),
    }


def _human(r: dict) -> str:
    o = []
    o.append("=" * 70)
    o.append(f" CONFLUENCE  {r['symbol']}  {r['tf']}   price={r['price']:.2f}   trend={r['trend']}")
    o.append(f" swing: low {r['swing']['low']:.2f} -> high {r['swing']['high']:.2f} (leg {r['swing']['leg']})")
    o.append(f" RSI {r['rsi']} ({r['rsi_state']}) | flow: {r['accumulation']} (OBV slope {r['obv_slope']:.0f}) | POC {r['poc']:.2f}")
    o.append(f" candles(20): {r['candles_20']['bull']} bull / {r['candles_20']['bear']} bear, last {r['candles_20']['last']}")
    o.append(f" EMA50 {r['ema50']:.2f} | EMA200 {r['ema200']:.2f}")
    o.append(" FIBO ALCISTA (supports):  " + "  ".join(f"{k}:{v}" for k, v in r['fib_bull'].items()))
    o.append(" FIBO BAJISTA (resist.):   " + "  ".join(f"{k}:{v}" for k, v in r['fib_bear'].items()))
    o.append(f" nearest: support {r['nearest']['fib_support']:.2f} | resistance {r['nearest']['fib_resistance']:.2f}")
    o.append(" -- PANORAMAS --")
    o.append(f"  ALCISTA: {r['scenarios']['bull']}")
    o.append(f"  BASE:    {r['scenarios']['base']}")
    o.append(f"  BAJISTA: {r['scenarios']['bear']}")
    o.append("=" * 70)
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="D")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    payload = json.load(sys.stdin)
    bars = payload.get("bars") or payload.get("ohlcv") or []
    if len(bars) < 30:
        raise SystemExit(f"need >= 30 bars, got {len(bars)}")
    r = analyze(bars, args.symbol, args.tf)
    print(json.dumps(r, indent=2) if args.json else _human(r))


if __name__ == "__main__":
    main()
