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
import contextlib
import json
import math
import os
import sys

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:                     # non-Unix: degrade to no locking
    _HAS_FCNTL = False


@contextlib.contextmanager
def _lock(path: str):
    """Advisory exclusive file lock around the log's read-modify-write, so the
    detached hook's `record` (append) and `score` (full rewrite) can't race and
    drop forecasts. No-op where fcntl is unavailable."""
    if not _HAS_FCNTL:
        yield
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lf = open(path + ".lock", "w")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()

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


DIR_EPS = 0.03   # p_up must be this far from 0.5 to count as a directional call
QUANTILE_LEVELS = (0.05, 0.25, 0.50, 0.75, 0.95)   # cone quantiles P5..P95


def pit(levels, values, y: float) -> float:
    """Probability Integral Transform: the forecast CDF (piecewise-linear through
    the quantile knots) evaluated at the realized `y`. A calibrated model's PIT is
    ~Uniform(0,1); a PIT histogram exposes bias / over- / under-dispersion."""
    if y <= values[0]:
        return float(levels[0])
    if y >= values[-1]:
        return float(levels[-1])
    for i in range(1, len(values)):
        if y <= values[i]:
            lo_v, hi_v = values[i - 1], values[i]
            lo_l, hi_l = levels[i - 1], levels[i]
            frac = (y - lo_v) / (hi_v - lo_v) if hi_v > lo_v else 0.0
            return float(lo_l + frac * (hi_l - lo_l))
    return float(levels[-1])


def pinball_loss(levels, values, y: float) -> float:
    """Mean quantile (pinball) loss over the forecast quantiles — a STRICTLY
    PROPER score, so it ranks cones (gaussian vs bootstrap vs student_t) honestly,
    unlike band coverage (which a merely-wider cone always 'wins'). Lower is better."""
    tot = 0.0
    for tau, q in zip(levels, values):
        d = y - q
        tot += tau * d if d >= 0 else (tau - 1.0) * d
    return tot / len(levels)


def _dir_hit(realized_close: float, S0: float, p_up: float):
    """Directional hit, or None when the cone makes no real directional call.
    Zero-drift cones sit at p_up ~ 0.5, so scoring direction there just recovers
    the base rate of up-moves (not skill); exact ties (realized == S0) are also
    undefined. Only |p_up - 0.5| > DIR_EPS and a non-tie realized are scored."""
    if abs(p_up - 0.5) <= DIR_EPS or realized_close == S0:
        return None
    return (realized_close > S0) == (p_up > 0.5)


def score_record(rec: dict, realized_close: float) -> dict:
    """Attach realized outcome + per-model band hits. Idempotent."""
    S0 = rec["S0"]
    realized = {"close": float(realized_close),
                "ret_pct": 100.0 * (realized_close / S0 - 1.0) if S0 else 0.0,
                "up": realized_close > S0, "models": {}}
    for m, c in rec["cones"].items():
        qv = [c["P5"], c["P25"], c["P50"], c["P75"], c["P95"]]
        realized["models"][m] = {
            "in_90": c["P5"] <= realized_close <= c["P95"],
            "in_50": c["P25"] <= realized_close <= c["P75"],
            "dir_hit": _dir_hit(realized_close, S0, c["p_up"]),
            "pit": pit(QUANTILE_LEVELS, qv, realized_close),
            "pinball": pinball_loss(QUANTILE_LEVELS, qv, realized_close),
        }
    out = dict(rec)
    out["realized"] = realized
    return out


def _dedupe(records: list) -> list:
    """Collapse exact duplicate forecasts (same symbol/tf/made_at/horizon); last wins.
    The hook can record the same window twice, which would double-count coverage."""
    seen = {}
    for r in records:
        key = (r.get("symbol"), r.get("tf"), r.get("made_at_unix"), r.get("horizon_bars"))
        seen[key] = r
    return list(seen.values())


def _independent_subset(records: list) -> list:
    """Greedy maximal set of NON-OVERLAPPING [made_at, target] windows (by target).
    Overlapping forecasts (recorded every few bars with multi-bar horizons) are not
    independent; this is the effective sample size for an honest coverage CI."""
    out, last_end = [], None
    for r in sorted(records, key=lambda x: x["target_unix"]):
        if last_end is None or r["made_at_unix"] >= last_end:
            out.append(r)
            last_end = r["target_unix"]
    return out


def _wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval for a proportion — honest at small n and near 0/1."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def calibration(records: list) -> dict:
    """Per-model coverage of the 90%/50% bands over scored records, with an
    effective-sample Wilson CI on the 90% coverage (overlapping forecasts are not
    independent, so the plain count overstates the evidence)."""
    records = _dedupe(records)
    scored = [r for r in records if r.get("realized")]
    indep = _independent_subset(scored)
    out = {"n_total": len(records), "n_scored": len(scored),
           "n_eff": len(indep), "models": {}}
    for m in MODELS:
        rows = [r["realized"]["models"][m] for r in scored
                if m in r["realized"].get("models", {})]
        if not rows:
            continue
        n = len(rows)
        stat = {
            "n": n,
            "cover_90": sum(x["in_90"] for x in rows) / n,
            "cover_50": sum(x["in_50"] for x in rows) / n,
        }
        # Honest CI: only the non-overlapping (independent) forecasts count.
        indep_rows = [r["realized"]["models"][m] for r in indep
                      if m in r["realized"].get("models", {})]
        if indep_rows:
            k90 = sum(x["in_90"] for x in indep_rows)
            stat["cover_90_ci"] = _wilson(k90, len(indep_rows))
        dh = [x["dir_hit"] for x in rows if x["dir_hit"] is not None]
        if dh:                                # only report direction when scored
            stat["dir_n"] = len(dh)
            stat["dir_acc"] = sum(dh) / len(dh)
        pb = [x["pinball"] for x in rows if "pinball" in x]
        if pb:                                # strictly-proper score for ranking
            stat["mean_pinball"] = sum(pb) / len(pb)
        out["models"][m] = stat
    return out


def coverage_table(records: list) -> dict:
    """Realized coverage grouped by 'symbol|tf|horizon' — the honest lookup that
    lets a live forecast report what its nominal band ACTUALLY covered for this
    instrument/horizon (calibration is symbol- and regime-specific, per the
    cross-symbol evidence). Keyed string -> {model: {cover_90, cover_50, n}}."""
    groups: dict = {}
    for r in records:
        if not r.get("realized"):
            continue
        key = f"{r.get('symbol')}|{r.get('tf')}|{r.get('horizon_bars')}"
        groups.setdefault(key, []).append(r)
    out = {}
    for key, recs in groups.items():
        cal = calibration(recs)
        out[key] = {m: {"cover_90": s["cover_90"], "cover_50": s["cover_50"], "n": s["n"]}
                    for m, s in cal["models"].items()}
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
    ap.add_argument("cmd", choices=["record", "score", "stats", "calibrate"])
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(DEFAULT_LOG), "calibration.json"),
                    help="calibrate: where to write the coverage table")
    args = ap.parse_args()

    if args.cmd == "calibrate":
        tbl = coverage_table(read_log(args.log))
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(tbl, f, indent=2)
        print(f"calibration table: {len(tbl)} symbol/horizon group(s) -> {args.out}")
        return

    if args.cmd == "record":
        report = json.load(sys.stdin)
        rec = build_record(report)
        with _lock(args.log):
            append_log(args.log, rec)
        print(f"recorded {rec['symbol']} {rec['tf']}m h={rec['horizon_bars']} "
              f"S0={rec['S0']:.2f} target_unix={rec['target_unix']} -> {args.log}")
        return

    if args.cmd == "score":
        bars = _bars_from_stdin()
        with _lock(args.log):                 # read-modify-write must be atomic vs the hook
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
        print(f"forecasts: {cal['n_scored']}/{cal['n_total']} scored  "
              f"(n_eff={cal['n_eff']} non-overlapping)  [{args.log}]")
        print(f"  {'model':<14}{'n':>5}{'cover90':>9}{'cover50':>9}{'pinball':>10}"
              f"{'cover90 CI':>16}{'dir_acc':>12}")
        for m, s in cal["models"].items():
            dir_s = f"{s['dir_acc']:.2f} (n={s['dir_n']})" if "dir_acc" in s else "n/a"
            pb_s = f"{s['mean_pinball']:.3f}" if "mean_pinball" in s else "n/a"
            ci = s.get("cover_90_ci")
            ci_s = f"[{ci[0]:.2f},{ci[1]:.2f}]" if ci else "n/a"
            print(f"  {m:<14}{s['n']:>5}{s['cover_90']:>9.2f}{s['cover_50']:>9.2f}"
                  f"{pb_s:>10}{ci_s:>16}{dir_s:>12}")
        print("  -> cover90 CI uses n_eff (independent forecasts); wide until n_eff grows.")
        print("  -> lower pinball = better-shaped cone (ranks the three models).")
        print("  -> cover90 should trend to ~0.90 and cover50 to ~0.50 if the cone")
        print("     is well-calibrated; persistently low coverage = vol underestimated.")


if __name__ == "__main__":
    main()
