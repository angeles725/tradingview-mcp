#!/usr/bin/env python3
"""
OHLCV collector — accumulate bars to disk beyond the ~300-bar live window.

The live feed returns only ~300 bars per timeframe, which is too few for
per-regime or per-condition statistics to reach n>=30 (see Block 7). This
collector MERGES each pull into a persistent per-(symbol,timeframe) CSV store,
de-duplicated by bar timestamp and kept sorted, so running it periodically
grows real history. It can also RE-EMIT the store as the same bars JSON the
analysis tools consume, so analyze/backtest/decide can run over the full
accumulated history instead of the last 300 bars.

Stdlib only (no numpy/pandas) so it runs unattended, e.g. from cron with the
base Python.

Usage:
    # accumulate: pull the live window and merge into the store
    node src/cli/index.js ohlcv --count 300 \
      | python analysis/collect.py --symbol XAUUSD --tf 15

    # inspect what has been accumulated
    python analysis/collect.py --stats

    # feed the FULL history into an analysis tool
    python analysis/collect.py --symbol XAUUSD --tf 15 --emit \
      | <venv>/python analysis/analyze.py --symbol XAUUSD --tf 15
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

FIELDS = ["time", "open", "high", "low", "close", "volume"]
DEFAULT_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _safe_name(symbol: str, tf: str) -> str:
    s = symbol.replace(":", "_").replace("/", "_").replace("\\", "_")
    return f"{s}_{tf}.csv"


def store_path(store_dir: str, symbol: str, tf: str) -> str:
    return os.path.join(store_dir, _safe_name(symbol, tf))


def load_store(path: str) -> dict:
    """Return {time(int): row(dict)} from an existing CSV store, or {}."""
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            t = int(float(r["time"]))
            rows[t] = {k: (int(float(r[k])) if k == "time" else float(r[k]))
                       for k in FIELDS}
    return rows


def merge(existing: dict, new_bars: list) -> tuple:
    """Merge new bars into the existing store (keyed by time). Returns
    (sorted_rows, n_new, n_updated). A repeated timestamp UPDATES the bar (the
    latest pull wins — the last live bar is often still forming)."""
    n_new = n_upd = 0
    for b in new_bars:
        t = int(float(b["time"]))
        row = {k: (t if k == "time" else float(b[k])) for k in FIELDS}
        if t in existing:
            if existing[t] != row:
                n_upd += 1
            existing[t] = row
        else:
            existing[t] = row
            n_new += 1
    ordered = [existing[t] for t in sorted(existing)]
    return ordered, n_new, n_upd


def save_store(path: str, rows: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)   # atomic — a crash never corrupts the store


def read_bars_stdin() -> list:
    payload = json.load(sys.stdin)
    return payload.get("bars") or payload.get("ohlcv") or []


def cmd_stats(store_dir: str) -> None:
    if not os.path.isdir(store_dir):
        print(f"(no store at {store_dir})")
        return
    files = sorted(f for f in os.listdir(store_dir) if f.endswith(".csv"))
    if not files:
        print(f"(store {store_dir} is empty)")
        return
    print(f"store: {store_dir}")
    for f in files:
        rows = load_store(os.path.join(store_dir, f))
        times = sorted(rows)
        span = f"{times[0]}..{times[-1]}" if times else "-"
        print(f"  {f:<28} {len(rows):>6} bars   time {span}")


def cmd_emit(path: str) -> None:
    rows = list(load_store(path).values())
    rows.sort(key=lambda r: r["time"])
    print(json.dumps({"success": True, "bar_count": len(rows),
                      "total_available": len(rows), "source": "store",
                      "bars": rows}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--store", default=DEFAULT_STORE, help="store directory")
    ap.add_argument("--stats", action="store_true", help="list accumulated stores")
    ap.add_argument("--emit", action="store_true",
                    help="print the store as bars JSON (no stdin read)")
    args = ap.parse_args()

    if args.stats:
        cmd_stats(args.store)
        return

    path = store_path(args.store, args.symbol, args.tf)
    if args.emit:
        cmd_emit(path)
        return

    new_bars = read_bars_stdin()
    if not new_bars:
        raise SystemExit("no bars on stdin to collect")
    existing = load_store(path)
    before = len(existing)
    ordered, n_new, n_upd = merge(existing, new_bars)
    save_store(path, ordered)
    print(f"collected {args.symbol} {args.tf}m: +{n_new} new, {n_upd} updated "
          f"-> {len(ordered)} total (was {before})  [{path}]")


if __name__ == "__main__":
    main()
