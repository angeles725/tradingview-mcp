#!/usr/bin/env python3
"""
Forecast log + calibration scorer — keep an honest record of what the cone
predicted and check, after the fact, how often reality landed inside the band.

A probabilistic forecast is only as good as its CALIBRATION: a 90% band should
contain the realized price ~90% of the time. This tool records each cone forecast
and later scores it against the realized close, so the coverage numbers become
evidence for improving the tools (too-narrow band -> underestimating vol, etc.).

Stdlib only — runs anywhere. `record` consumes an analyze.py --json report (whose
cone math is canonical and gap-aware); `score` consumes a fresh OHLCV pull.

Usage:
    # 1) record a forecast (cone from analyze, self-contained via last_bar_unix)
    node src/cli/index.js ohlcv -n 300 \
      | <venv>/python analysis/analyze.py --symbol XAUUSD --tf 15 --horizon 4 --json \
      | python analysis/forecast.py record

    # 2) later, score any matured forecasts against a fresh pull
    node src/cli/index.js ohlcv -n 300 \
      | python analysis/forecast.py score

    # 3) calibration so far (coverage of the 90% / 50% bands, per model)
    python analysis/forecast.py stats
"""

from __future__ import annotations

import argparse
import json
import os
import sys

MODELS = ("gaussian", "bootstrap", "student_t")
DEFAULT_LOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "corpus", "forecasts.jsonl")


# --------------------------------------------------------------------------- #
# Pure helpers (testable without I/O)
# --------------------------------------------------------------------------- #
def build_record(report: dict) -> dict:
    """Turn an analyze.py --json report into a forecast record. Needs the report
    to carry last_bar_unix and bar_step_sec (added for self-contained forecasts)."""
    step = int(report.get("bar_step_sec") or 0)
    horizon = int(report["horizon_bars"])
    made = int(report.get("last_bar_unix") or 0)
    mc = report["monte_carlo"]
    cones = {m: {q: mc[m][q] for q in ("P5", "P25", "P50", "P75", "P95", "p_up", "model")}
             for m in MODELS if m in mc}
    return {
        "symbol": report["symbol"], "tf": report["timeframe"],
        "horizon_bars": horizon, "bar_step_sec": step,
        "made_at_unix": made, "target_unix": made + step * horizon,
        "S0": float(report["last_price"]),
        "cross_gap_dropped": report.get("cross_gap_dropped", 0),
        "cones": cones, "realized": None,
    }


def score_record(rec: dict, realized_close: float) -> dict:
    """Attach realized outcome + per-model band hits. Idempotent."""
    S0 = rec["S0"]
    realized = {"close": float(realized_close),
                "ret_pct": 100.0 * (realized_close / S0 - 1.0) if S0 else 0.0,
                "up": realized_close > S0, "models": {}}
    for m, c in rec["cones"].items():
        realized["models"][m] = {
            "in_90": c["P5"] <= realized_close <= c["P95"],
            "in_50": c["P25"] <= realized_close <= c["P75"],
            # directional call was right if the median side matched (zero-drift
            # cones sit ~flat, so this is mostly a tie-breaker, recorded for honesty)
            "dir_hit": (realized_close > S0) == (c["p_up"] >= 0.5),
        }
    out = dict(rec)
    out["realized"] = realized
    return out


def calibration(records: list) -> dict:
    """Per-model coverage of the 90%/50% bands over scored records."""
    scored = [r for r in records if r.get("realized")]
    out = {"n_total": len(records), "n_scored": len(scored), "models": {}}
    for m in MODELS:
        rows = [r["realized"]["models"][m] for r in scored
                if m in r["realized"].get("models", {})]
        if not rows:
            continue
        n = len(rows)
        out["models"][m] = {
            "n": n,
            "cover_90": sum(x["in_90"] for x in rows) / n,
            "cover_50": sum(x["in_50"] for x in rows) / n,
            "dir_acc": sum(x["dir_hit"] for x in rows) / n,
        }
    return out


def nearest_close(bars: list, target_unix: int, tol: int) -> float | None:
    """Close of the bar whose time is closest to target_unix within tol, else None."""
    best, best_d = None, None
    for b in bars:
        d = abs(int(float(b["time"])) - target_unix)
        if d <= tol and (best_d is None or d < best_d):
            best, best_d = float(b["close"]), d
    return best


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
def read_log(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def write_log(path: str, records: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, path)


def append_log(path: str, rec: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def _bars_from_stdin() -> list:
    payload = json.load(sys.stdin)
    return payload.get("bars") or payload.get("ohlcv") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "score", "stats"])
    ap.add_argument("--log", default=DEFAULT_LOG)
    args = ap.parse_args()

    if args.cmd == "record":
        report = json.load(sys.stdin)
        rec = build_record(report)
        append_log(args.log, rec)
        print(f"recorded {rec['symbol']} {rec['tf']}m h={rec['horizon_bars']} "
              f"S0={rec['S0']:.2f} target_unix={rec['target_unix']} -> {args.log}")
        return

    if args.cmd == "score":
        bars = _bars_from_stdin()
        records = read_log(args.log)
        n_scored = 0
        for i, r in enumerate(records):
            if r.get("realized"):
                continue
            tol = max(int(r.get("bar_step_sec") or 0) // 2, 1)
            rc = nearest_close(bars, int(r["target_unix"]), tol)
            if rc is not None:
                records[i] = score_record(r, rc)
                n_scored += 1
        write_log(args.log, records)
        print(f"scored {n_scored} newly-matured forecast(s) [{args.log}]")
        return

    if args.cmd == "stats":
        cal = calibration(read_log(args.log))
        print(f"forecasts: {cal['n_scored']}/{cal['n_total']} scored  [{args.log}]")
        print(f"  {'model':<14}{'n':>5}{'cover90':>9}{'cover50':>9}{'dir_acc':>9}")
        for m, s in cal["models"].items():
            print(f"  {m:<14}{s['n']:>5}{s['cover_90']:>9.2f}{s['cover_50']:>9.2f}"
                  f"{s['dir_acc']:>9.2f}")
        print("  -> cover90 should trend to ~0.90 and cover50 to ~0.50 if the cone")
        print("     is well-calibrated; persistently low coverage = vol underestimated.")


if __name__ == "__main__":
    main()
