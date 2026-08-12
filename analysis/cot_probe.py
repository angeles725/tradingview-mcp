#!/usr/bin/env python3
"""
COT positioning EDGE PROBE — is CFTC positioning an orthogonal directional edge?

Price-derived momentum was proven no-skill (direction_significance.py). COT
(Commitments of Traders) is genuinely orthogonal: it reports WHO is positioned,
not price. The thesis: commercials (hedgers, "smart money") at a positioning
EXTREME lead the next move. This probe tests it honestly with the SAME machinery
that killed the momentum edge — no double standard.

Method:
  1. Fetch the full weekly COT history for a market (CFTC Socrata API, no auth).
  2. Commercial NET = comm_long - comm_short. COT INDEX = rolling percentile of
     the net over `lookback` weeks (0..1), the standard positioning normaliser.
  3. Emit a directional call ONLY at an extreme: index >= up_thresh -> up,
     <= down_thresh -> down (the middle is 'no signal', skipped). confidence =
     how far past the threshold (the thesis says edge lives at the extremes).
  4. Align each COT date to the proxy price (weekly closes on stdin) and score
     the realized direction `horizon` weeks forward.
  5. Run direction_significance.skill_test: skill vs base rate, cluster/perm CI.

Ship a COT signal ONLY if skill CI > 0 and permutation p < 0.05 — same bar as
everything else. Usage:
    node src/cli/index.js ohlcv --count 800 --timeframe W --expect-symbol OANDA:XAUUSD \
      | python analysis/cot_probe.py --market "GOLD - COMMODITY EXCHANGE INC." \
          --symbol OANDA:XAUUSD --horizon 4
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

import numpy as np

import direction_significance as sig

SOCRATA = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"


def fetch_cot(market: str, limit: int = 5000) -> list:
    """All weekly COT rows for a market, oldest first. Legacy futures-only."""
    q = {
        "$select": ("report_date_as_yyyy_mm_dd,comm_positions_long_all,"
                    "comm_positions_short_all,noncomm_positions_long_all,"
                    "noncomm_positions_short_all,open_interest_all"),
        "$where": f"market_and_exchange_names='{market}'",
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": str(limit),
    }
    url = SOCRATA + "?" + urllib.parse.urlencode(q, safe="=,")
    with urllib.request.urlopen(url, timeout=30) as r:
        rows = json.load(r)
    out = []
    for d in rows:
        try:
            out.append({
                "date": d["report_date_as_yyyy_mm_dd"][:10],
                "comm_net": float(d["comm_positions_long_all"]) - float(d["comm_positions_short_all"]),
                "noncomm_net": float(d["noncomm_positions_long_all"]) - float(d["noncomm_positions_short_all"]),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return out


def cot_index(net: np.ndarray, lookback: int) -> np.ndarray:
    """Rolling percentile (0..1) of the net position within its trailing window.
    NaN until `lookback` observations exist (no lookahead — trailing only)."""
    n = net.size
    out = np.full(n, np.nan)
    for i in range(lookback - 1, n):
        w = net[i - lookback + 1:i + 1]
        lo, hi = w.min(), w.max()
        out[i] = (net[i] - lo) / (hi - lo) if hi > lo else 0.5
    return out


def _iso_to_unix(dates: list) -> np.ndarray:
    # avoid Date.now / tz surprises: parse YYYY-MM-DD to a day ordinal in seconds
    import datetime
    epoch = datetime.date(1970, 1, 1)
    return np.array([(datetime.date(int(d[:4]), int(d[5:7]), int(d[8:10])) - epoch).days * 86400.0
                     for d in dates], dtype=float)


def build_records(cot: list, signal: str, lookback: int, up_thresh: float,
                  down_thresh: float, closes: np.ndarray, ctimes: np.ndarray,
                  horizon: int, symbol: str) -> list:
    net = np.array([c[signal] for c in cot], float)
    idx = cot_index(net, lookback)
    ctimes_price = np.asarray(ctimes, float)
    closes = np.asarray(closes, float)
    cdates = _iso_to_unix([c["date"] for c in cot])
    recs = []
    for i in range(cot.__len__()):
        ci = idx[i]
        if not (ci == ci):                       # NaN warm-up
            continue
        if ci >= up_thresh:
            bias, conf = "up", (ci - up_thresh) / (1.0 - up_thresh + 1e-9)
        elif ci <= down_thresh:
            bias, conf = "down", (down_thresh - ci) / (down_thresh + 1e-9)
        else:
            continue                             # no extreme -> no signal
        # align to price: first weekly close at/after the COT date, and horizon ahead.
        # skip COT dates outside the price window (else they collapse onto bar 0).
        if cdates[i] < ctimes_price[0] or cdates[i] > ctimes_price[-1]:
            continue
        j = int(np.searchsorted(ctimes_price, cdates[i], side="left"))
        if j >= closes.size or j + horizon >= closes.size:
            continue
        d = closes[j + horizon] - closes[j]
        rd = 1 if d > 0 else -1 if d < 0 else 0
        pred = 1 if bias == "up" else -1
        recs.append({"tf": "W", "bias": bias, "confidence": round(float(min(conf, 1.0)), 3),
                     "realized_dir": rd, "hit": 1 if pred == rd else 0, "symbol": symbol})
    return recs


def main():
    ap = argparse.ArgumentParser(description="COT positioning edge probe")
    ap.add_argument("--market", required=True)
    ap.add_argument("--symbol", required=True, help="price proxy symbol (for labeling)")
    ap.add_argument("--signal", default="comm_net", choices=["comm_net", "noncomm_net"])
    ap.add_argument("--lookback", type=int, default=156, help="COT-index window (weeks)")
    ap.add_argument("--up-thresh", type=float, default=0.8)
    ap.add_argument("--down-thresh", type=float, default=0.2)
    ap.add_argument("--horizon", type=int, default=4, help="forward weeks")
    ap.add_argument("--n-boot", type=int, default=4000)
    ap.add_argument("--emit", action="store_true",
                    help="print the scored records as JSONL (for pooling) instead of the report")
    args = ap.parse_args()

    payload = json.load(sys.stdin)
    bars = payload.get("bars") or payload.get("ohlcv") or []
    if len(bars) < 30:
        raise SystemExit(f"need weekly price bars on stdin, got {len(bars)}")
    closes = np.array([b["close"] for b in bars], float)
    ctimes = np.array([b.get("time", i) for i, b in enumerate(bars)], float)

    cot = fetch_cot(args.market)
    recs = build_records(cot, args.signal, args.lookback, args.up_thresh,
                         args.down_thresh, closes, ctimes, args.horizon, args.symbol)

    if args.emit:
        for r in recs:
            print(json.dumps(r))
        return

    print(f"=== COT EDGE PROBE  {args.symbol}  ({args.signal}, h={args.horizon}w) ===")
    print(f"  COT rows={len(cot)}  price bars={len(bars)}  extreme signals={len(recs)}")
    res = sig.skill_test(recs, n_boot=args.n_boot)
    print(sig._fmt("COT", res))
    # high-extreme subset — the thesis says edge concentrates at the extremes
    hi = sig.skill_test(recs, min_conf=0.5, n_boot=args.n_boot)
    if not hi.get("insufficient"):
        print(sig._fmt("COT", hi, tag=" [conf>=0.5]"))


if __name__ == "__main__":
    main()
