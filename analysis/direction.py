#!/usr/bin/env python3
"""
Multi-timeframe DIRECTIONAL BIAS — the honest answer to "up or down?".

The cones in analyze.py are deliberately ZERO-DRIFT: they measure the size of
the uncertainty, not its sign. This module is the complement the user asked for:
a per-timeframe LEAN (up / down / flat) with an EXPLICIT confidence, so a weak
signal cannot pose as a strong one.

WHY confidence, not a naked arrow: this project already validated (2026-08-10,
95 resolved forecasts, block bootstrap) that trading the forecast direction had
NO EDGE intraday. So the honest design refuses to fake certainty at short
horizons — the `TF_RELIABILITY` prior caps intraday confidence hard, and the
flat threshold sends near-noise reads to "flat" instead of a coin-flip arrow.
The real signal is ALIGNMENT: when the higher timeframes agree, that agreement
is the tradeable information — a lone 1m arrow is not.

Directional content comes ONLY from signals that carry sign information, each
reused verbatim from quant.py (single source of truth, already unit-tested):
  - OLS trend slope + HAC significance   (structural direction)
  - rolling-regression regime label      (trend-up / trend-down / chop)
  - Lo-MacKinlay variance ratio          (momentum vs mean-reversion => confidence)
  - EMA50/EMA200 stack vs price          (structural direction)
  - OBV slope                            (order-flow direction)
  - RSI(14) distance from 50             (mild tilt only)

Stdlib + numpy/scipy (same deps as quant.py). Reads TradingView OHLCV JSON on
stdin, exactly like analyze.py.

Usage:
    node src/cli/index.js ohlcv --count 300 --expect-symbol OANDA:XAUUSD \
      | python analysis/direction.py --symbol OANDA:XAUUSD --tf 15
    # emits one JSON bias record. Collect several TFs, then:
    cat records.jsonl | python analysis/direction.py aggregate
"""
import argparse
import json
import math
import sys

import numpy as np

import quant as q

# Confidence ceiling per timeframe. Encodes the validated intraday no-edge
# finding: the shorter the bar, the less a directional read can be trusted, so
# its confidence is multiplied down. D/W/M keep full weight; 1m is quartered.
TF_RELIABILITY = {
    "1": 0.25, "3": 0.30, "5": 0.35, "15": 0.45, "30": 0.55,
    "60": 0.65, "120": 0.72, "240": 0.80,
    "D": 0.90, "1D": 0.90, "W": 1.0, "1W": 1.0, "M": 1.0, "1M": 1.0,
}

# Human labels for the canonical resolutions, high -> low.
TF_ORDER = ["M", "W", "D", "240", "60", "15", "5", "1"]
TF_LABEL = {"M": "1 mes", "W": "1 semana", "D": "1 dia", "240": "4h",
            "60": "1 hora", "30": "30m", "15": "15 min", "5": "5m", "1": "1 min"}

# Below this |net_score|/total_weight the read is too weak to call a direction:
# report "flat" rather than a coin flip. Same idea as decide.py's Gate A refusing
# an insignificant trend.
FLAT_STRENGTH = 0.15
FLAT_CONFIDENCE = 0.20
CONF_CEIL = 0.95        # never claim certainty, however aligned the votes are


def load_bars(stream) -> dict:
    """Parse TradingView OHLCV JSON (same shape analyze.py expects)."""
    payload = json.load(stream)
    bars = payload.get("bars") or payload.get("data") or payload
    if not isinstance(bars, list) or not bars:
        raise ValueError("no bars on stdin")
    arr = {k: np.array([b[k] for b in bars], dtype=float)
           for k in ("open", "high", "low", "close", "volume")}
    arr["time"] = np.array([b.get("time", i) for i, b in enumerate(bars)],
                           dtype=float)
    return arr


def _tf_reliability(tf: str) -> float:
    return TF_RELIABILITY.get(str(tf), 0.5)


def bias_from_bars(o, h, l, c, v, times, tf: str) -> dict:
    """
    Compute the directional bias for ONE timeframe from its OHLCV arrays.

    Returns a self-describing record: the bias, the confidence, and every
    component that fed them, so the read is auditable — never a black-box arrow.
    """
    c = np.asarray(c, dtype=float)
    n = c.size
    if n < 5:
        raise ValueError(f"need >=5 bars, got {n}")
    price = float(c[-1])

    # --- component signals (all from quant.py) -----------------------------
    trend = q.ols_trend(c)
    slope_sign = 1.0 if trend.slope > 0 else -1.0 if trend.slope < 0 else 0.0

    regime = str(q.classify_regime(c, window=min(20, n - 1))[-1])
    regime_val = {"trend-up": 1.0, "trend-down": -1.0, "chop": 0.0}.get(regime, 0.0)

    ret = q.log_returns(c, times=times)
    if ret.size >= 8:
        vr, vr_z, _ = q.variance_ratio_test(ret, 4, times=times)
    else:
        vr, vr_z = float("nan"), float("nan")

    ema50 = float(q.ema(c, 50)[-1]) if n >= 50 else float("nan")
    ema200 = float(q.ema(c, 200)[-1]) if n >= 200 else float("nan")

    v = np.asarray(v, dtype=float)
    obv = q.obv(c, v)
    look = min(20, n - 1)
    obv_slope = float(obv[-1] - obv[-1 - look]) if look > 0 else 0.0

    rsi_arr = q.rsi_wilder(c, 14)
    rsi_valid = rsi_arr[~np.isnan(rsi_arr)]
    rsi = float(rsi_valid[-1]) if rsi_valid.size else float("nan")

    # --- weighted directional votes ----------------------------------------
    # Each (weight, value in [-1,1]); net_score / total_weight = strength [0,1].
    votes = []

    # Trend: strong when significant, heavily discounted when it is just a noisy
    # sloped line (Granger-Newbold spurious regression is handled inside ols_trend).
    trend_val = slope_sign * (1.0 if trend.significant else 0.25)
    votes.append(("trend", 2.0, trend_val))

    votes.append(("regime", 1.5, regime_val))

    # EMA stack: price and the 50/200 relationship. Full weight only when both
    # EMAs exist and agree; a half-vote when only EMA50 is available (n<200).
    if ema200 == ema200:  # not NaN
        if price > ema200 and ema50 > ema200:
            ema_val = 1.0
        elif price < ema200 and ema50 < ema200:
            ema_val = -1.0
        else:
            ema_val = 0.5 * (1.0 if price > ema200 else -1.0)
        votes.append(("ema_stack", 1.5, ema_val))
    elif ema50 == ema50:
        votes.append(("ema_stack", 0.75, 0.5 * (1.0 if price > ema50 else -1.0)))

    votes.append(("obv", 1.0, 1.0 if obv_slope > 0 else -1.0 if obv_slope < 0 else 0.0))

    if rsi == rsi:  # not NaN — mild tilt only, clipped
        votes.append(("rsi", 0.5, float(np.clip((rsi - 50.0) / 50.0, -1.0, 1.0))))

    total_weight = sum(w for _, w, _ in votes)
    net_score = sum(w * val for _, w, val in votes)
    strength = abs(net_score) / total_weight if total_weight > 0 else 0.0

    # --- confidence: strength, tempered by significance / momentum / TF prior --
    sig_factor = 1.0 if trend.significant else 0.6

    direction = 1.0 if net_score > 0 else -1.0 if net_score < 0 else 0.0
    vr_factor = 1.0
    if vr == vr and vr_z == vr_z:
        if vr > 1.0 and vr_z > 1.645:
            vr_factor = 1.10          # momentum confirms persistence
        elif vr < 1.0 and vr_z < -1.645:
            vr_factor = 0.75          # mean-reverting: the current lean may fade

    tf_prior = _tf_reliability(tf)
    confidence = min(CONF_CEIL, strength * sig_factor * vr_factor * tf_prior)

    if strength < FLAT_STRENGTH or confidence < FLAT_CONFIDENCE or direction == 0:
        bias = "flat"
    else:
        bias = "up" if direction > 0 else "down"

    return {
        "tf": str(tf),
        "bias": bias,
        "confidence": round(confidence, 3),
        "price": round(price, 5),
        "components": {
            "trend_slope": trend.slope,
            "trend_r2": round(trend.r2, 3),
            "trend_significant": bool(trend.significant),
            "regime": regime,
            "vr4": None if vr != vr else round(vr, 3),
            "vr4_z": None if vr_z != vr_z else round(vr_z, 3),
            "ema50": None if ema50 != ema50 else round(ema50, 5),
            "ema200": None if ema200 != ema200 else round(ema200, 5),
            "obv_slope": round(obv_slope, 1),
            "rsi": None if rsi != rsi else round(rsi, 1),
        },
        "strength": round(strength, 3),
        "n_bars": int(n),
    }


def aggregate(records: list) -> dict:
    """
    Combine per-TF bias records into an overall lean. The signal is ALIGNMENT:
    a confidence-weighted vote across timeframes, reported with how many TFs
    actually agree. A lone intraday arrow cannot move the verdict much because
    its confidence is small by construction.
    """
    directional = [r for r in records if r.get("bias") in ("up", "down")]
    agg = sum((1.0 if r["bias"] == "up" else -1.0) * r["confidence"]
              for r in directional)
    n_up = sum(1 for r in records if r.get("bias") == "up")
    n_down = sum(1 for r in records if r.get("bias") == "down")
    n_flat = sum(1 for r in records if r.get("bias") == "flat")

    # Higher-timeframe consensus (D/W/M) is the trustworthy part; surface it.
    hi = [r for r in records if str(r.get("tf")) in ("D", "1D", "W", "1W", "M", "1M")]
    hi_up = sum(1 for r in hi if r.get("bias") == "up")
    hi_down = sum(1 for r in hi if r.get("bias") == "down")

    if abs(agg) < 0.15:
        overall = "flat/mixed"
    else:
        overall = "up" if agg > 0 else "down"

    return {
        "overall": overall,
        "agg_score": round(agg, 3),
        "n_up": n_up, "n_down": n_down, "n_flat": n_flat,
        "hi_tf_up": hi_up, "hi_tf_down": hi_down, "n_hi_tf": len(hi),
    }


def _fmt_table(records: list, symbol: str) -> str:
    order = {tf: i for i, tf in enumerate(TF_ORDER)}
    recs = sorted(records, key=lambda r: order.get(str(r["tf"]), 99))
    arrow = {"up": "^ up  ", "down": "v down", "flat": "~ flat"}
    out = []
    out.append("=" * 70)
    out.append(f" SESGO DIRECCIONAL  {symbol}   (honesto: confianza explicita)")
    out.append("=" * 70)
    out.append(f" {'TF':<9}{'SESGO':<8}{'CONF':<7}NOTA")
    out.append(" " + "-" * 66)
    for r in recs:
        cp = r.get("components", {})
        note = f"{cp.get('regime','?')}"
        if cp.get("trend_significant"):
            note += f" (trend sig R2={cp.get('trend_r2')})"
        else:
            note += f" (R2={cp.get('trend_r2')} no sig)"
        if r["confidence"] < 0.20:
            note += " -- ruido, ignorar"
        out.append(f" {TF_LABEL.get(str(r['tf']), str(r['tf'])):<9}"
                   f"{arrow.get(r['bias'],'?'):<8}{r['confidence']:<7.2f}{note}")
    ag = aggregate(records)
    out.append(" " + "-" * 66)
    out.append(f" ALINEACION: {ag['n_up']} alcista / {ag['n_down']} bajista / "
               f"{ag['n_flat']} plano  |  TFs altos (D/W/M): "
               f"{ag['hi_tf_up']} up / {ag['hi_tf_down']} down")
    out.append(f" SESGO GENERAL: {ag['overall'].upper()}  (score {ag['agg_score']})")
    out.append("=" * 70)
    out.append(" Recordatorio: esto es un SESGO probabilistico, NO una garantia.")
    out.append(" Los conos (analyze.py) siguen siendo zero-drift. En 1m/15m la")
    out.append(" confianza es baja a proposito (validado: sin edge intradia).")
    out.append(" Tu tomas la decision.")
    out.append("=" * 70)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Multi-timeframe directional bias")
    sub = ap.add_argument
    ap.add_argument("mode", nargs="?", default="bias",
                    choices=["bias", "aggregate"],
                    help="bias: one TF from stdin OHLCV; aggregate: table from JSONL")
    ap.add_argument("--symbol", default="")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--json", action="store_true",
                    help="bias mode: emit the JSON record (default). Adds symbol/tf.")
    ap.add_argument("--human", action="store_true", help="bias mode: human line")
    args = ap.parse_args()

    if args.mode == "aggregate":
        records = []
        symbol = args.symbol
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            records.append(r)
            symbol = symbol or r.get("symbol", "")
        if not records:
            print("(no records on stdin)", file=sys.stderr)
            sys.exit(1)
        print(_fmt_table(records, symbol or "?"))
        return

    data = load_bars(sys.stdin)
    rec = bias_from_bars(data["open"], data["high"], data["low"],
                         data["close"], data["volume"], data["time"], args.tf)
    rec["symbol"] = args.symbol
    if args.human:
        cp = rec["components"]
        print(f"{args.symbol} {args.tf}: {rec['bias'].upper()} "
              f"conf={rec['confidence']} | {cp['regime']} "
              f"R2={cp['trend_r2']} sig={cp['trend_significant']} "
              f"VR4={cp['vr4']} RSI={cp['rsi']}")
    else:
        print(json.dumps(rec))


if __name__ == "__main__":
    main()
