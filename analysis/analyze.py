#!/usr/bin/env python3
"""
Honest, range-based chart assessment. Reads TradingView OHLCV JSON on stdin
(the shape emitted by `node src/cli/index.js ohlcv --count N`) and prints a
structured report: trend with significance, several volatility estimators, a
three-model Monte Carlo cone, and conditional next-bar probabilities with
confidence intervals.

Usage:
    node src/cli/index.js ohlcv --count 300 \
        | <venv>/python analysis/analyze.py --symbol XAUUSD --tf 15 --horizon 16

This tool NEVER predicts direction. It sizes the move and attaches a
probability. Read analysis/README.md for the guardrails.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

import quant as q


# 15m bars over a 24h metals/forex session -> 96 bars/day.
DEFAULT_BARS_PER_DAY = {
    "1": 1440, "3": 480, "5": 288, "15": 96, "30": 48,
    "60": 24, "120": 12, "240": 6, "D": 1,
}


def load_bars(stream) -> dict:
    payload = json.load(stream)
    bars = payload.get("bars") or payload.get("ohlcv") or []
    if not bars:
        raise SystemExit("no bars in input (expected a `bars` array)")
    arr = {k: np.array([b[k] for b in bars], dtype=float)
           for k in ("open", "high", "low", "close", "volume")}
    arr["_meta"] = {
        "bar_count": payload.get("bar_count", len(bars)),
        "total_available": payload.get("total_available"),
    }
    return arr


def build_conditions(closes, opens, rsi, ret):
    """
    Boolean masks on the DECISION bar t, aligned to `target_up` (did t+1 close
    up?). Every condition may only use information available AT the close of bar
    t — never t+1 — or the study leaks the answer (lookahead bias) and prints a
    fake 100% edge. `up_at[t]` is the move INTO bar t (close_t > close_{t-1}),
    which is known at t; the target is the move OUT of bar t (t -> t+1).
    """
    n = closes.size
    target_up = (np.diff(closes) > 0)   # index t: close_{t+1} > close_t
    T = target_up.size                  # decision bars 0..T-1  (= n-1)

    up_at = np.zeros(n, dtype=bool)
    up_at[1:] = np.diff(closes) > 0     # up_at[t]: close_t > close_{t-1} (past)

    body = closes - opens               # known at close of bar t
    conds = {}
    r = rsi[:T]
    conds["RSI<30 (oversold)"] = (r < 30)
    conds["RSI>70 (overbought)"] = (r > 70)
    conds["RSI 30-70 (neutral)"] = (r >= 30) & (r <= 70)
    conds["bull candle (C>O)"] = (body[:T] > 0)
    conds["bear candle (C<O)"] = (body[:T] < 0)

    # 3 consecutive up bars ENDING at t (uses only up_at, i.e. past/present).
    three = np.zeros(T, dtype=bool)
    for t in range(2, T):
        three[t] = up_at[t] and up_at[t - 1] and up_at[t - 2]
    conds["3 up bars in a row"] = three
    return conds, target_up


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="15", help="timeframe key for bars/day scaling")
    ap.add_argument("--horizon", type=int, default=16, help="forward bars for the cone")
    ap.add_argument("--rsi-period", type=int, default=14)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    data = load_bars(sys.stdin)
    o, h, l, c = data["open"], data["high"], data["low"], data["close"]
    n = c.size
    ret = q.log_returns(c)
    bars_per_day = DEFAULT_BARS_PER_DAY.get(args.tf, 96)

    # --- Trend -----------------------------------------------------------
    trend = q.ols_trend(c)

    # --- Volatility (per-bar sigma from several estimators) --------------
    v_cc = q.close_to_close_vol(ret)
    v_ewma = q.ewma_vol(ret)
    v_park = q.parkinson_vol(h, l)
    v_gk = q.garman_klass_vol(o, h, l, c)
    garch = q.garch11_vol(ret)
    v_garch = garch[0] if garch else None

    # Cone uses the conditional estimator (clustering-aware): GARCH if it fit,
    # else EWMA. This is the honest "volatility of NOW".
    sigma_cone = v_garch if v_garch else v_ewma
    daily_pct = q.scale_sigma(sigma_cone, bars_per_day) * 100

    # --- RSI -------------------------------------------------------------
    rsi = q.rsi_wilder(c, args.rsi_period)
    rsi_now = rsi[-1]

    # --- Monte Carlo cones (3 tail models) -------------------------------
    S0 = float(c[-1])
    cone_g = q.mc_gaussian(S0, sigma_cone, args.horizon, 0.0, seed=args.seed)
    cone_b = q.mc_bootstrap(S0, ret, args.horizon, seed=args.seed)
    cone_t = q.mc_student_t(S0, ret, args.horizon, seed=args.seed)

    # --- Regime (trending vs mean-reverting) -----------------------------
    regime_labels = q.classify_regime(c, window=20)
    regime_now = str(regime_labels[-1])
    uniq, counts = np.unique(regime_labels, return_counts=True)
    regime_mix = {str(k): int(v) for k, v in zip(uniq, counts)}
    vr = {k: q.variance_ratio(ret, k) for k in (2, 4, 8)}

    # --- Conditional probabilities ---------------------------------------
    baseline = float(np.mean(np.diff(c) > 0))
    conds, next_up = build_conditions(c, o, rsi, ret)
    cond_objs = [q.conditional_next_up(name, mask, next_up, baseline)
                 for name, mask in conds.items()]
    # Correct for multiple testing: with several conditions each judged at 0.05,
    # the family-wise false-positive rate balloons. BH-FDR re-labels the verdicts.
    q.correct_conditionals(cond_objs, alpha=0.05)
    n_tested = sum(1 for cnd in cond_objs
                   if cnd.verdict != "thin-sample" and cnd.p_value == cnd.p_value)
    conditionals = [cnd.as_dict() for cnd in cond_objs]

    report = {
        "symbol": args.symbol,
        "timeframe": args.tf,
        "bars": int(n),
        "total_available": data["_meta"]["total_available"],
        "last_price": S0,
        "horizon_bars": args.horizon,
        "trend": trend.as_dict(),
        "volatility_per_bar": {
            "close_to_close": v_cc, "ewma_0.94": v_ewma,
            "parkinson": v_park, "garman_klass": v_gk,
            "garch11": v_garch, "garch_params": garch[1] if garch else None,
            "cone_sigma_used": sigma_cone,
            "implied_daily_pct": daily_pct,
        },
        "rsi": {"period": args.rsi_period, "now": None if np.isnan(rsi_now) else float(rsi_now)},
        "regime": {"now": regime_now, "mix": regime_mix, "variance_ratio": vr},
        "monte_carlo": {"gaussian": cone_g, "bootstrap": cone_b, "student_t": cone_t},
        "baseline_next_up": baseline,
        "conditionals": conditionals,
        "conditionals_correction": {
            "method": "benjamini_hochberg", "alpha": 0.05, "n_tested": n_tested,
        },
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return

    _print_human(report)


def _fmt(x, d=2):
    return f"{x:.{d}f}" if isinstance(x, (int, float)) and x == x else str(x)


def _print_human(r):
    W = 74
    print("=" * W)
    print(f" HONEST ASSESSMENT  {r['symbol']}  {r['timeframe']}m   "
          f"n={r['bars']} bars (of {r['total_available']} avail)")
    print(f" Last price: {r['last_price']:.3f}   |   cone horizon: {r['horizon_bars']} bars")
    print("=" * W)

    t = r["trend"]
    sig = "SIGNIFICANT" if t["significant"] else "NOT significant (noise)"
    print(f"\nTREND ({sig})")
    print(f"  OLS slope   : {t['slope']:+.4f} price/bar   R^2={t['r2']:.2f}   t={t['t_stat']:+.1f}")
    print(f"  slope 95%CI : [{t['ci95'][0]:+.4f}, {t['ci95'][1]:+.4f}]")
    print(f"  Theil-Sen   : {t['theilsen']:+.4f} price/bar  (robust cross-check)")
    if t["r2"] < 0.30:
        print("  -> R^2 below 0.30: treat the slope as noise, not a signal.")

    v = r["volatility_per_bar"]
    print("\nVOLATILITY (per-bar log-return sigma)")
    print(f"  close-to-close : {v['close_to_close']*100:.3f}%")
    print(f"  EWMA(0.94)     : {v['ewma_0.94']*100:.3f}%   (conditional / clustering-aware)")
    print(f"  Parkinson      : {v['parkinson']*100:.3f}%   (OHLC range)")
    print(f"  Garman-Klass   : {v['garman_klass']*100:.3f}%   (most efficient)")
    if v["garch11"]:
        gp = v["garch_params"]
        print(f"  GARCH(1,1)     : {v['garch11']*100:.3f}%   "
              f"(a={gp['alpha']:.2f} b={gp['beta']:.2f}, persist={gp['alpha']+gp['beta']:.2f})")
    print(f"  -> implied daily move ~ +/-{v['implied_daily_pct']:.2f}%  (1 sigma)")

    rsi = r["rsi"]["now"]
    print(f"\nMOMENTUM   RSI(14, Wilder) = {_fmt(rsi,1)}   "
          f"(corroboration only; high RSI != sell in a trend)")

    rg = r["regime"]
    vr = rg["variance_ratio"]
    mix = "  ".join(f"{k}:{v}" for k, v in sorted(rg["mix"].items()))
    print(f"\nREGIME   now = {rg['now']}")
    print(f"  window mix   : {mix}")
    print(f"  variance ratio: VR2={_fmt(vr[2],2)}  VR4={_fmt(vr[4],2)}  VR8={_fmt(vr[8],2)}   "
          f"(>1 trending/momentum, <1 mean-reverting, ~1 random)")

    print(f"\nMONTE CARLO CONE  ({r['horizon_bars']} bars ahead, zero-drift)")
    print(f"  {'model':<22}{'P5':>10}{'P25':>10}{'P50':>10}{'P75':>10}{'P95':>10}{'P(up)':>8}")
    for key in ("gaussian", "bootstrap", "student_t"):
        m = r["monte_carlo"][key]
        print(f"  {m['model']:<22}{m['P5']:>10.2f}{m['P25']:>10.2f}{m['P50']:>10.2f}"
              f"{m['P75']:>10.2f}{m['P95']:>10.2f}{m['p_up']:>8.2f}")
    print("  -> deliver the BAND (e.g. 90% inside P5..P95), never the median.")
    print("  -> if bootstrap/t P5..P95 is WIDER than gaussian, tails are fat: size down.")

    corr = r.get("conditionals_correction", {})
    print(f"\nCONDITIONAL P(next bar up)   baseline = {r['baseline_next_up']:.3f}")
    print(f"  {'condition':<24}{'n':>5}{'rate':>8}{'95% CI':>16}{'edge':>8}{'p':>8}{'p_adj':>8}  verdict")
    for cnd in r["conditionals"]:
        ci = f"[{cnd['ci95'][0]:.2f},{cnd['ci95'][1]:.2f}]"
        pv = _fmt(cnd["p_value"], 3)
        padj = _fmt(cnd.get("p_adjusted"), 3)
        print(f"  {cnd['name']:<24}{cnd['n']:>5}{cnd['rate']:>8.2f}{ci:>16}"
              f"{cnd['edge']:>+8.2f}{pv:>8}{padj:>8}  {cnd['verdict']}")
    print("  -> 'thin-sample' (n<30) or a CI straddling baseline = NO edge.")
    if corr:
        print(f"  -> verdict is FDR-corrected ({corr.get('method')}, "
              f"{corr.get('n_tested')} tests): a lone p<0.05 is NOT an edge.")
    print("=" * W)
    print("Guardrail: no line above predicts DIRECTION. This sizes the move and")
    print("attaches a probability. Risk management and an honest backtest decide P&L.")
    print("=" * W)


if __name__ == "__main__":
    main()
