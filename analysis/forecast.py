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
# Cross-symbol contamination guard: nearest_close matches on TIME only, so a
# mis-filtered multi-symbol window can hand a record another symbol's price. A
# realized move beyond this fraction of S0 is not real for these instruments and
# horizons -> refuse to score and leave the record pending for a correct source.
MAX_REALIZED_JUMP = 0.20
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


def trade_levels(cone: dict, side: str, entry: float = None) -> dict:
    """Stop-loss / take-profit and risk measures derived from the forecast CONE
    (the honest source: the band, not a guessed level). Long: SL at the downside
    P5, TP at the upside P95. Short: mirrored. `entry` defaults to the cone median
    P50. Returns entry, stop_loss, take_profit, risk/reward distances, R:R, and
    SL/TP distances in %."""
    P5, P95 = float(cone["P5"]), float(cone["P95"])
    e = float(entry) if entry is not None else float(cone["P50"])
    if side == "long":
        sl, tp = P5, P95
        risk, reward = e - sl, tp - e
    elif side == "short":
        sl, tp = P95, P5
        risk, reward = sl - e, e - tp
    else:
        raise ValueError("side must be 'long' or 'short'")
    rr = (reward / risk) if risk > 0 else float("inf")
    return {
        "side": side, "entry": e, "stop_loss": sl, "take_profit": tp,
        "risk": risk, "reward": reward, "rr": rr,
        "sl_pct": abs(e - sl) / e * 100 if e else float("nan"),
        "tp_pct": abs(tp - e) / e * 100 if e else float("nan"),
    }


def size_for_risk(levels: dict, equity: float, risk_pct: float = 1.0) -> dict:
    """Position size from a fixed-fractional risk budget and the trade_levels stop.
    Risk `risk_pct`% of `equity`; units = risk_cash / stop-distance. Returns units,
    cash at risk, notional, cash reward at the take-profit, leverage, and R:R. A
    zero stop-distance yields zero units (never divides by zero)."""
    entry = float(levels["entry"]); sl = float(levels["stop_loss"]); tp = float(levels["take_profit"])
    risk_cash = equity * risk_pct / 100.0
    per_unit = abs(entry - sl)
    units = (risk_cash / per_unit) if per_unit > 0 else 0.0
    notional = units * entry
    return {
        "equity": equity, "risk_pct": risk_pct, "risk_cash": risk_cash,
        "units": units, "notional": notional,
        "reward_cash": units * abs(tp - entry),
        "leverage": (notional / equity) if equity else float("inf"),
        "rr": levels.get("rr", float("nan")),
    }


def crps_from_quantiles(levels, values, y: float) -> float:
    """CRPS approximated from the stored quantile forecast. CRPS = 2 * integral of
    the quantile (pinball) loss over tau in (0,1); this trapezoid-integrates the
    per-level pinball across the stored levels (tails beyond the outer quantiles
    truncated). One number for FULL-distribution calibration — complements pinball
    at fixed levels, and weights by the tau-spacing the flat mean ignores. Lower is
    better; comparable across models."""
    pl = []
    for tau, q in zip(levels, values):
        d = y - q
        pl.append(tau * d if d >= 0 else (tau - 1.0) * d)
    integral = 0.0
    for i in range(1, len(levels)):
        integral += (levels[i] - levels[i - 1]) * (pl[i] + pl[i - 1]) / 2.0
    return 2.0 * integral


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
            # normalized to bps of S0 so pinball is comparable across symbols/prices
            "pinball_bps": (pinball_loss(QUANTILE_LEVELS, qv, realized_close) / S0 * 1e4)
                           if S0 else float("nan"),
            "crps": crps_from_quantiles(QUANTILE_LEVELS, qv, realized_close),
            "crps_bps": (crps_from_quantiles(QUANTILE_LEVELS, qv, realized_close) / S0 * 1e4)
                        if S0 else float("nan"),
        }
    out = dict(rec)
    out["realized"] = realized
    return out


def _dedupe(records: list) -> list:
    """Collapse forecasts that predict the SAME (symbol, tf, horizon, target_unix).
    Overlapping hook ticks can record the same target hour more than once, which
    would double-count coverage. Keying on target (not made_at) folds those away:
    two forecasts only share a target if built from the same last bar, so they are
    genuinely redundant. A SCORED copy always beats an unscored one (else
    calibration silently drops the realized outcome); among copies of equal
    scored-status, the freshest forecast (latest made_at) wins."""
    seen = {}
    for r in records:
        key = (r.get("symbol"), r.get("tf"), r.get("horizon_bars"), r.get("target_unix"))
        prev = seen.get(key)
        if prev is None:
            seen[key] = r
            continue
        r_scored = r.get("realized") is not None
        p_scored = prev.get("realized") is not None
        if r_scored != p_scored:
            if r_scored:                                     # scored beats unscored
                seen[key] = r
        elif (r.get("made_at_unix") or 0) >= (prev.get("made_at_unix") or 0):
            seen[key] = r                                    # equal status: freshest wins
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
        # Honest CI: only the non-overlapping (independent) forecasts count. The
        # POOLED cover_50/cover_90 over autocorrelated 15m forecasts overstates the
        # evidence (a quiet regime keeps price inside the band), so BOTH bands get a
        # Wilson CI over the independent subset — read the CI, not the raw fraction.
        indep_rows = [r["realized"]["models"][m] for r in indep
                      if m in r["realized"].get("models", {})]
        if indep_rows:
            stat["n_eff"] = len(indep_rows)
            k90 = sum(x["in_90"] for x in indep_rows)
            stat["cover_90_ci"] = _wilson(k90, len(indep_rows))
            k50 = sum(x["in_50"] for x in indep_rows)
            stat["cover_50_ci"] = _wilson(k50, len(indep_rows))
        dh = [x["dir_hit"] for x in rows if x["dir_hit"] is not None]
        if dh:                                # only report direction when scored
            stat["dir_n"] = len(dh)
            stat["dir_acc"] = sum(dh) / len(dh)
        pb = [x["pinball"] for x in rows if "pinball" in x]
        if pb:                                # strictly-proper score for ranking
            stat["mean_pinball"] = sum(pb) / len(pb)
        pbb = [x["pinball_bps"] for x in rows if x.get("pinball_bps") == x.get("pinball_bps")
               and "pinball_bps" in x]
        if pbb:                               # bps-normalized -> comparable across symbols
            stat["mean_pinball_bps"] = sum(pbb) / len(pbb)
        crb = [x["crps_bps"] for x in rows if x.get("crps_bps") == x.get("crps_bps")
               and "crps_bps" in x]
        if crb:                               # full-distribution score, bps-normalized
            stat["mean_crps_bps"] = sum(crb) / len(crb)
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
# Conformal calibration layer — turn the coverage DIAGNOSTIC into an active
# CORRECTION with a finite-sample marginal-coverage guarantee (split conformal /
# CQR, Vovk; Romano et al. 2019). The band diagnostics say IF the cone is
# miscalibrated; this says BY HOW MUCH to widen (or tighten) it to hit nominal.
# --------------------------------------------------------------------------- #
_BAND_SPEC = {"90": ("P5", "P95", 0.90), "50": ("P25", "P75", 0.50)}


def conformal_delta(scores, level: float) -> float:
    """Split-conformal radius: the smallest Q such that at least `level` of the
    nonconformity `scores` are <= Q. That is the ceil((n+1)*level)-th order
    statistic (clamped to the max when the index exceeds n — the finite-sample
    correction that yields the >= level coverage guarantee). Empty -> 0."""
    s = sorted(float(x) for x in scores)
    n = len(s)
    if n == 0:
        return 0.0
    idx = math.ceil((n + 1) * level)
    if idx > n:
        return s[-1]
    if idx < 1:
        return s[0]
    return s[idx - 1]


def conformalize_band(records: list, model: str, band: str,
                      adaptive: bool = False, gamma: float = 0.05) -> dict:
    """For one model's `band` ('90'|'50'), compute the conformal correction from
    scored records and report coverage BEFORE and AFTER applying it. Nonconformity
    is E_i = max(lo - y, y - hi) / S0 (return-space, so it is scale-free across a
    symbol's price); the additive correction is delta_frac. Adjusted band per
    record = [lo - delta_frac*S0, hi + delta_frac*S0]. delta_frac may be negative
    (an over-wide band is tightened). cover_adj >= level on the calibration set by
    construction.

    With `adaptive=True`, the split-conformal delta is taken at the ACI-adapted
    coverage level (aci_adapted_level) instead of the fixed nominal level, so a live
    regime shift that starts breaking the band widens the correction automatically.
    The static-level delta is still reported as `static_delta_frac` for reference."""
    lo_k, hi_k, level = _BAND_SPEC[band]
    data, scores = [], []
    for r in records:
        if not r.get("realized") or model not in r.get("cones", {}):
            continue
        cone = r["cones"][model]
        S0 = r.get("S0") or 0.0
        if not S0:
            continue
        lo, hi = float(cone[lo_k]), float(cone[hi_k])
        y = float(r["realized"]["close"])
        scores.append(max(lo - y, y - hi) / S0)
        data.append((lo, hi, y, S0))
    n = len(data)
    if n == 0:
        return {"n": 0, "level": level, "delta_frac": 0.0, "delta_bps": 0.0,
                "cover_raw": None, "cover_adj": None}
    lvl = aci_adapted_level(records, model, band, gamma) if adaptive else level
    delta = conformal_delta(scores, lvl)
    cov_raw = sum(1 for lo, hi, y, _ in data if lo <= y <= hi) / n
    cov_adj = sum(1 for lo, hi, y, S0 in data
                  if (lo - delta * S0) <= y <= (hi + delta * S0)) / n
    out = {"n": n, "level": level, "delta_frac": delta, "delta_bps": delta * 1e4,
           "cover_raw": cov_raw, "cover_adj": cov_adj}
    if adaptive:
        out["aci_level"] = lvl
        out["static_delta_frac"] = conformal_delta(scores, level)
    return out


def conformal_validate(records: list, model: str, band: str,
                       train_frac: float = 0.7, min_n: int = 20) -> dict | None:
    """Walk-forward (out-of-sample) check of the conformal correction: learn the
    delta on the FIRST `train_frac` of the records (by made_at) and MEASURE coverage
    on the held-out remainder after applying it. Unlike conformalize_band (which
    reports in-sample-of-the-correction coverage), this tells you whether the
    correction GENERALIZES. Returns None below `min_n` scored records."""
    lo_k, hi_k, level = _BAND_SPEC[band]
    rows = [r for r in records
            if r.get("realized") and model in r.get("cones", {}) and r.get("S0")]
    rows.sort(key=lambda r: r.get("made_at_unix", 0))
    if len(rows) < min_n:
        return None
    cut = int(len(rows) * train_frac)
    train, test = rows[:cut], rows[cut:]
    if not train or not test:
        return None

    def nonconf(r):
        c = r["cones"][model]
        return max(float(c[lo_k]) - float(r["realized"]["close"]),
                   float(r["realized"]["close"]) - float(c[hi_k])) / float(r["S0"])

    delta = conformal_delta([nonconf(r) for r in train], level)

    def covered(r, d):
        c = r["cones"][model]; y = float(r["realized"]["close"]); S0 = float(r["S0"])
        return (float(c[lo_k]) - d * S0) <= y <= (float(c[hi_k]) + d * S0)

    n = len(test)
    cov_raw = sum(covered(r, 0.0) for r in test) / n
    cov_adj = sum(covered(r, delta) for r in test) / n
    return {"n_train": len(train), "n_test": n, "level": level,
            "delta_frac": delta, "delta_bps": delta * 1e4,
            "cover_raw_test": cov_raw, "cover_adj_test": cov_adj}


def aci_next_alpha(alpha: float, target_alpha: float, covered: bool,
                   gamma: float = 0.05) -> float:
    """Adaptive Conformal Inference online update (Gibbs & Candes 2021):
    alpha_{t+1} = alpha_t + gamma*(target_alpha - err_t), err_t = 0 if covered
    else 1. A MISS lowers alpha (widen next interval); a HIT raises it (allow
    tightening). Clamped to [0,1]. `alpha` is miscoverage (= 1 - nominal level)."""
    err = 0.0 if covered else 1.0
    a = alpha + gamma * (target_alpha - err)
    return min(1.0, max(0.0, a))


def aci_adapted_level(records: list, model: str, band: str,
                      gamma: float = 0.05) -> float:
    """Replay ACI (Gibbs-Candes 2021) over a group's scored records in made_at
    order, starting from the nominal miscoverage, and return the ADAPTED coverage
    level (1 - alpha_T) to use for the NEXT forecast's split-conformal delta. A run
    of raw-band MISSES lowers alpha -> raises the level -> conformal_delta picks a
    higher order statistic (wider band); HITS relax it back toward nominal. Clamped
    to [0.5, 0.999] so a streak can neither collapse nor explode the band. Empty or
    single-group input returns the nominal level unchanged."""
    lo_k, hi_k, level = _BAND_SPEC[band]
    rows = [r for r in records
            if r.get("realized") and model in r.get("cones", {}) and r.get("S0")]
    rows.sort(key=lambda r: r.get("made_at_unix", 0))
    if not rows:
        return level
    target_alpha = 1.0 - level
    alpha = target_alpha
    for r in rows:
        c = r["cones"][model]
        y = float(r["realized"]["close"])
        covered = float(c[lo_k]) <= y <= float(c[hi_k])
        alpha = aci_next_alpha(alpha, target_alpha, covered, gamma)
    return min(0.999, max(0.5, 1.0 - alpha))


def apply_conformal_widening(cone: dict, delta90_frac: float, delta50_frac: float,
                             S0: float) -> dict:
    """Return a copy of a cone with its 90% (P5/P95) and 50% (P25/P75) bands
    shifted OUT by the conformal deltas (in price = delta_frac*S0), leaving P50 and
    p_up untouched. Re-sorts the five quantiles so the band stays monotone even if
    a (negative) tightening delta would otherwise cross them."""
    d90, d50 = delta90_frac * S0, delta50_frac * S0
    vals = sorted([cone["P5"] - d90, cone["P25"] - d50, cone["P50"],
                   cone["P75"] + d50, cone["P95"] + d90])
    out = dict(cone)
    out["P5"], out["P25"], out["P50"], out["P75"], out["P95"] = (float(v) for v in vals)
    return out


def conformal_report(records: list, min_n: int = 8, adaptive: bool = False) -> dict:
    """Per 'symbol|tf|horizon' -> per model -> per band conformal correction, over
    groups with at least `min_n` scored records (tail calibration is unreliable
    below that). Mirrors coverage_table's grouping.

    `adaptive=False` (default, SHIPPED) uses the static split-conformal delta. The
    ACI-adapted variant (`adaptive=True`) is available but NOT shipped: a
    walk-forward check (tvdecision B22) showed it OVER-FITS out-of-sample — its
    gamma-step over-tightens the over-covering markets below nominal (mean OOS
    cover90 0.84 vs 0.92 static / 0.94 raw), the same failure the 50%-band
    correction showed in B20. Kept as machinery for future regime-aware work."""
    records = _dedupe(records)
    groups: dict = {}
    for r in records:
        if not r.get("realized"):
            continue
        key = f"{r.get('symbol')}|{r.get('tf')}|{r.get('horizon_bars')}"
        groups.setdefault(key, []).append(r)
    out: dict = {}
    for key, recs in groups.items():
        models: dict = {}
        for m in MODELS:
            bands = {}
            for band in ("90", "50"):
                cb = conformalize_band(recs, m, band, adaptive=adaptive)
                if cb["n"] >= min_n:
                    bands[band] = cb
            if bands:
                models[m] = bands
        if models:
            out[key] = models
    return out


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


def _store_bars(store_dir: str, symbol: str, tf: str) -> list:
    """Load collect.py's persistent CSV store for (symbol, tf) as a time-sorted
    bars list. Empty list when no store exists for that symbol/timeframe."""
    import collect
    rows = list(collect.load_store(collect.store_path(store_dir, symbol, str(tf))).values())
    rows.sort(key=lambda r: r["time"])
    return rows


def s0_contaminated(symbol: str, tf, s0: float, store_dir: str,
                    max_dev: float = 0.5) -> bool:
    """RECORD-side cross-symbol contamination guard. A feed-not-ready symbol switch
    can hand a record another symbol's bars (EURUSD ~1.15 recorded at SPX's ~7757).
    Compare S0 to the symbol's OWN persistent-store median close: a deviation beyond
    `max_dev` means the pull almost certainly belongs to another symbol. Returns
    False (can't judge) when there is no store reference or S0 is missing — never a
    false reject on a thin store."""
    if not s0:
        return False
    try:
        rows = _store_bars(store_dir, symbol, tf)
    except Exception:
        return False
    closes = sorted(float(b["close"]) for b in rows
                    if b.get("close") not in (None, "") and float(b["close"]) > 0)
    if len(closes) < 20:
        return False
    med = closes[len(closes) // 2]
    return med > 0 and abs(s0 / med - 1.0) > max_dev


def score_pending(records: list, bars: list = None, store_dir: str = None,
                  symbol: str = None) -> tuple:
    """Score every unrealized record in place and return (records, n_scored).

    Two sources, so a matured forecast is never lost or mis-scored:
      - store_dir: score each record against ITS OWN symbol+tf persistent store
        (collect.py). Symbol-correct by construction, and it covers forecasts that
        have scrolled off the ~300-bar live window.
      - bars: a single live window. Because nearest_close matches on TIME ONLY, a
        multi-symbol log would otherwise score one symbol against another's bars —
        so a `symbol` filter is REQUIRED-in-spirit here: pass it to restrict which
        records these bars may realize.
    """
    n = 0
    cache = {}
    for i, r in enumerate(records):
        if r.get("realized"):
            continue
        if symbol is not None and r.get("symbol") != symbol:
            continue
        if store_dir is not None:
            key = (r["symbol"], str(r["tf"]))
            if key not in cache:
                cache[key] = _store_bars(store_dir, r["symbol"], r["tf"])
            src = cache[key]
        else:
            src = bars or []
        tol = max(int(r.get("bar_step_sec") or 0) // 2, 1)
        rc = nearest_close(src, int(r["target_unix"]), tol)
        if rc is not None:
            S0 = r.get("S0")
            if S0 and abs(rc / S0 - 1.0) > MAX_REALIZED_JUMP:
                continue   # cross-symbol contamination: refuse, stay pending
            records[i] = score_record(r, rc)
            n += 1
    return records, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "score", "stats", "calibrate", "conformal"])
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(DEFAULT_LOG), "calibration.json"),
                    help="calibrate: where to write the coverage table")
    ap.add_argument("--conformal-out",
                    default=os.path.join(os.path.dirname(DEFAULT_LOG), "conformal.json"),
                    help="conformal: where to write the per-band correction table")
    ap.add_argument("--min-n", type=int, default=20,
                    help="conformal: minimum scored records per group to emit a correction")
    ap.add_argument("--extra-log", action="append", default=None,
                    help="conformal: additional log(s) to POOL with --log before computing "
                         "corrections (e.g. a backfill log, to reach min_n sooner). Repeatable.")
    ap.add_argument("--validate", action="store_true",
                    help="conformal: walk-forward OOS check (learn delta on train, measure "
                         "coverage on held-out test) instead of writing the table.")
    ap.add_argument("--store", default=None,
                    help="score: score against collect.py's persistent CSV store dir "
                         "(per symbol/tf) instead of a live window on stdin")
    ap.add_argument("--symbol", default=None,
                    help="score: only score records for this symbol (guards the stdin "
                         "path against cross-symbol mis-scoring)")
    args = ap.parse_args()

    if args.cmd == "calibrate":
        tbl = coverage_table(read_log(args.log))
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(tbl, f, indent=2)
        print(f"calibration table: {len(tbl)} symbol/horizon group(s) -> {args.out}")
        return

    if args.cmd == "conformal":
        recs = read_log(args.log)
        for extra in (args.extra_log or []):        # pool a backfill log to reach min_n
            recs += read_log(extra)
        if args.validate:
            recs = _dedupe(recs)
            groups: dict = {}
            for r in recs:
                if r.get("realized"):
                    groups.setdefault(f"{r.get('symbol')}|{r.get('tf')}|{r.get('horizon_bars')}", []).append(r)
            print(f"conformal WALK-FORWARD validation (train 70% -> test 30%, min_n={args.min_n})")
            print(f"  {'group':22}{'band':>5}{'nTest':>7}{'raw':>7}{'adj_oos':>9}{'delta_bps':>11}")
            any_row = False
            for key in sorted(groups):
                for band in ("90", "50"):
                    v = conformal_validate(groups[key], "gaussian", band, min_n=args.min_n)
                    if v:
                        any_row = True
                        print(f"  {key:22}{band:>5}{v['n_test']:>7}{v['cover_raw_test']:>7.2f}"
                              f"{v['cover_adj_test']:>9.2f}{v['delta_bps']:>+11.1f}")
            if not any_row:
                print("  (no group has >= min_n scored forecasts yet — pool a backfill log)")
            return
        rep = conformal_report(recs, min_n=args.min_n)
        out_path = args.conformal_out
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(rep, f, indent=2)
        print(f"conformal corrections: {len(rep)} group(s) "
              f"(min_n={args.min_n}) -> {out_path}")
        for key, models in rep.items():
            for m, bands in models.items():
                b = bands.get("90")
                if b:
                    print(f"  {key}  {m:<10} 90%: cover {b['cover_raw']:.2f}"
                          f"->{b['cover_adj']:.2f}  delta {b['delta_bps']:+.1f}bps "
                          f"(n={b['n']})")
        if not rep:
            print("  (no group has >= min_n scored forecasts yet — keep collecting)")
        return

    if args.cmd == "record":
        report = json.load(sys.stdin)
        rec = build_record(report)
        # Cross-symbol contamination guard: with a --store reference, refuse to
        # record an S0 that is wildly off the symbol's own history (a feed-not-ready
        # switch race handed us another symbol's bars). Better a skipped tick than a
        # poisoned calibration record that can never mature correctly.
        if args.store and s0_contaminated(rec["symbol"], rec["tf"], rec["S0"], args.store):
            print(f"SKIP contaminated {rec['symbol']} {rec['tf']}m S0={rec['S0']:.4f} "
                  f"(>50% off store median — wrong-symbol pull) -> not recorded")
            return
        with _lock(args.log):
            append_log(args.log, rec)
        print(f"recorded {rec['symbol']} {rec['tf']}m h={rec['horizon_bars']} "
              f"S0={rec['S0']:.2f} target_unix={rec['target_unix']} -> {args.log}")
        return

    if args.cmd == "score":
        # Source: the persistent store (per-symbol, covers off-window forecasts)
        # or a single live window on stdin (restricted to --symbol to avoid
        # scoring one symbol's forecast against another's bars at the same time).
        bars = None if args.store else _bars_from_stdin()
        with _lock(args.log):                 # read-modify-write must be atomic vs the hook
            records = read_log(args.log)
            records, n_scored = score_pending(records, bars=bars,
                                              store_dir=args.store, symbol=args.symbol)
            # fold away same-target duplicates left by overlapping ticks so the
            # persisted log stays clean (scored copies and freshest cones survive)
            records = _dedupe(records)
            write_log(args.log, records)
        src = f"store {args.store}" if args.store else "live window"
        print(f"scored {n_scored} newly-matured forecast(s) from {src} [{args.log}]")
        return

    if args.cmd == "stats":
        cal = calibration(read_log(args.log))
        print(f"forecasts: {cal['n_scored']}/{cal['n_total']} scored  "
              f"(n_eff={cal['n_eff']} non-overlapping)  [{args.log}]")
        print(f"  {'model':<14}{'n':>5}{'cover90':>9}{'cover50':>9}{'pinball_bps':>12}"
              f"{'crps_bps':>10}{'cover90 CI':>16}{'cover50 CI':>16}{'dir_acc':>12}")
        for m, s in cal["models"].items():
            dir_s = f"{s['dir_acc']:.2f} (n={s['dir_n']})" if "dir_acc" in s else "n/a"
            pb_s = f"{s['mean_pinball_bps']:.1f}" if "mean_pinball_bps" in s else "n/a"
            cr_s = f"{s['mean_crps_bps']:.1f}" if "mean_crps_bps" in s else "n/a"
            ci90 = s.get("cover_90_ci")
            ci90_s = f"[{ci90[0]:.2f},{ci90[1]:.2f}]" if ci90 else "n/a"
            ci50 = s.get("cover_50_ci")
            ci50_s = f"[{ci50[0]:.2f},{ci50[1]:.2f}]" if ci50 else "n/a"
            print(f"  {m:<14}{s['n']:>5}{s['cover_90']:>9.2f}{s['cover_50']:>9.2f}"
                  f"{pb_s:>12}{cr_s:>10}{ci90_s:>16}{ci50_s:>16}{dir_s:>12}")
        print("  -> BOTH CIs use n_eff (independent forecasts): read the CI, not the raw")
        print("     cover fraction — the pooled count over overlapping 15m forecasts inflates it.")
        print("  -> lower pinball_bps = better-shaped cone, comparable across symbols/horizons.")
        print("  -> cover90 should trend to ~0.90 and cover50 to ~0.50 if the cone")
        print("     is well-calibrated; persistently low coverage = vol underestimated.")


if __name__ == "__main__":
    main()
