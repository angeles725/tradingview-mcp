#!/usr/bin/env python3
"""
Decision engine — composes the whole toolkit into a single stance:
BUY / SELL / NO-TRADE, with the reason for every gate and honest sizing.

SAFETY (non-negotiable, enforced by omission):
    This module NEVER places an order. It does not import the tv CLI, does not
    call replay_trade, and does not touch any broker. It only READS bars on
    stdin and PRINTS a recommendation. It exists to improve the process with
    honest feedback (paper only), per the project's demo-before-real-money rule.

The default stance is NO-TRADE. A trade is proposed only when EVERY gate passes:
    A. a statistically significant trend, an aligned regime, and VR>1 momentum;
    B. a cost-surviving net edge for that direction (bootstrap CI clears zero);
    C. a risk/reward from the Monte Carlo cone at or above the threshold.
Position size comes from a fixed risk fraction over the stop distance — never
from conviction.

Usage:
    node src/cli/index.js ohlcv --count 300 \
      | <venv>/python analysis/decide.py --symbol XAUUSD --tf 15
    # historical feedback (walk the bars, tally what the process would have done):
    ... | <venv>/python analysis/decide.py --simulate
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict

import numpy as np

import quant as q
import backtest as bt


@dataclass
class Config:
    horizon: int = 16          # forward bars for the cone / trade window
    bars_per_day: int = 96
    r2_floor: float = 0.30     # trend significance floor
    vr_k: int = 4              # variance-ratio lag for the momentum check
    vr_z: float = 1.645        # min Lo-MacKinlay z for VR>1 to count as momentum
    cost_bps: float = 1.0      # per-side spread/cost (bps); set to broker/gold reality
    slip_frac: float = 0.0     # adverse stop slippage as a price fraction (market fills)
    min_rr: float = 1.5        # minimum reward:risk
    stop_k: float = 1.0        # stop distance in cone-sigma (horizon-scaled) units
    risk_frac: float = 0.01    # fraction of equity risked per trade
    equity: float = 10_000.0
    max_leverage: float = 10.0 # notional cap = max_leverage * equity (sizing guard)
    ema_period: int = 20


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str


@dataclass
class Stance:
    action: str                # BUY | SELL | NO-TRADE
    confidence: str            # low | medium | high | none
    reason: str                # the headline (first failing gate, or the setup)
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rr: float | None = None
    size_units: float | None = None
    risk_cash: float | None = None
    gates: list = field(default_factory=list)

    def as_dict(self):
        d = asdict(self)
        return d


def _no_trade(reason, gates, confidence="none"):
    return Stance(action="NO-TRADE", confidence=confidence, reason=reason, gates=gates)


def decide(o, h, l, c, cfg: Config, edge_override=None, times=None,
           sigma_override=None) -> Stance:
    """Return a Stance. edge_override lets the historical sim skip the (slow)
    per-bar backtest by supplying a precomputed edge decision for Gate B."""
    gates: list = []
    n = c.size
    if n < max(cfg.ema_period, 30) + cfg.horizon:
        return _no_trade("insufficient bars for a decision", gates)

    ret = q.log_returns(c, times=times)   # gap-aware (drops cross-gap returns) for vol/cones
    ret_raw = q.log_returns(c)            # raw, aligned to `times`, for segmented VR
    trend = q.ols_trend(c, cfg.r2_floor)
    regime = str(q.classify_regime(c, window=20)[-1])
    vr, vr_z, _ = q.variance_ratio_test(ret_raw, cfg.vr_k, times=times)
    direction = 1 if trend.slope > 0 else -1
    want_regime = "trend-up" if direction > 0 else "trend-down"

    # --- Gate A: significant, aligned, momentum-confirmed direction ----------
    # Momentum requires VR>1 AND a significant Lo-MacKinlay z — VR=1.01 with z~0
    # is noise, not a trend to chase.
    momentum = np.isfinite(vr) and np.isfinite(vr_z) and vr > 1.0 and vr_z >= cfg.vr_z
    a_ok = trend.significant and regime == want_regime and momentum
    gates.append(asdict(Gate("A_direction", a_ok,
                      f"trend {'sig' if trend.significant else 'NOT sig'} "
                      f"(R^2={trend.r2:.2f}), regime={regime} (want {want_regime}), "
                      f"VR{cfg.vr_k}={vr:.2f} (z={vr_z:.2f})")))
    if not a_ok:
        return _no_trade("no defensible direction (Gate A)", gates)

    # --- Gate B: cost-surviving net edge for this direction ------------------
    if edge_override is None:
        rule_sig = bt.rule_ema_trend(o, h, l, c, period=cfg.ema_period,
                                     direction=direction)
        net, cost = bt.simulate(rule_sig, o, c, cfg.horizon, cfg.cost_bps,
                                direction=direction)
        bstats = bt.compute_stats(net, cost)
        edge_ok = bstats.verdict == "edge"
        b_detail = (f"n={bstats.n}, exp={bstats.expectancy_bps:+.1f}bps, "
                    f"CI=[{bstats.ci95_ret[0]*1e4:+.1f},{bstats.ci95_ret[1]*1e4:+.1f}], "
                    f"verdict={bstats.verdict}")
    else:
        edge_ok, b_detail = edge_override[0], edge_override[1]
        # The override may carry the direction it was validated for; if that
        # disagrees with the direction we're about to trade (a slope flip between
        # the precondition bar and now), the edge does not apply — veto Gate B.
        edge_dir = edge_override[2] if len(edge_override) > 2 else direction
        if edge_dir != 0 and edge_dir != direction:
            edge_ok = False
            b_detail = (f"{b_detail} — direction flip "
                        f"(validated {edge_dir:+d}, trading {direction:+d})")
    gates.append(asdict(Gate("B_edge", edge_ok, b_detail)))
    if not edge_ok:
        return _no_trade("no cost-surviving edge in this direction (Gate B)", gates)

    # --- Gate C: risk/reward from the volatility cone ------------------------
    if sigma_override is not None:
        sigma_bar = sigma_override          # throttled fit from simulate_process
    else:
        sigma_bar = q.garch11_vol(ret)
        sigma_bar = sigma_bar[0] if sigma_bar else q.ewma_vol(ret)
    # Scale to the horizon honoring serial correlation at that horizon; Gate A
    # already established VR>1, so sqrt(h) alone would understate horizon vol.
    vr_h = q.variance_ratio(ret_raw, cfg.horizon, times=times)
    sigma_h = q.scale_sigma(sigma_bar, cfg.horizon, vr=vr_h)
    entry = float(c[-1])
    # The stop is a RISK-CONTROL level (vol-based, VR-aware) — a stop is a chosen
    # loss tolerance, not a forecast. The TARGET and the EV come from ONE edge-aware
    # cone: mc_block with drift (Gate A established a significant directional edge)
    # and momentum (block bootstrap). A zero-drift cone makes every EV ~0 (martingale)
    # so the engine would never trade; carrying the edge makes the EV honest AND real.
    cone = q.mc_block(entry, ret, cfg.horizon, drift_zero=False)
    if direction > 0:
        stop = entry * np.exp(-cfg.stop_k * sigma_h)
        target = cone["P75"]
    else:
        stop = entry * np.exp(cfg.stop_k * sigma_h)
        target = cone["P25"]
    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = reward / risk if risk > 0 else 0.0
    # First-passage EV under the same edge-aware distribution (drift_zero=False):
    # RR alone ignores that the stop may be touched FIRST more often than the target.
    bp = q.barrier_hit_probabilities(entry, o, h, l, c, cfg.horizon, stop, target,
                                     direction, drift_zero=False, times=times)
    ev = bp["p_target"] * reward - bp["p_stop"] * risk
    # EV must clear zero by more than its MC sampling error, so the gate is not
    # decided by Monte-Carlo noise (single-seed p_target/p_stop carry error ~1/sqrt(n)).
    se_ev = _ev_se(reward, risk, bp["p_target"], bp["p_stop"], bp.get("n", 0))
    c_ok = rr >= cfg.min_rr and np.isfinite(ev) and ev > se_ev
    gates.append(asdict(Gate("C_risk_reward", c_ok,
                      f"entry={entry:.2f} stop={stop:.2f} target={target:.2f} "
                      f"R:R={rr:.2f} (min {cfg.min_rr})  "
                      f"P(tgt)={bp['p_target']:.2f} P(stop)={bp['p_stop']:.2f} "
                      f"EV={ev:+.2f}±{se_ev:.2f}")))
    if not c_ok:
        why = (f"reward:risk {rr:.2f} below {cfg.min_rr}" if rr < cfg.min_rr
               else f"EV {ev:+.2f} not clear of MC noise (±{se_ev:.2f})")
        return _no_trade(f"{why} (Gate C)", gates)

    # --- All gates passed: size by fixed risk, capped by leverage ------------
    risk_cash = cfg.risk_frac * cfg.equity
    size, risk_cash = _position_size(risk_cash, risk, entry, cfg.equity, cfg.max_leverage)
    confidence = _confidence(bp["p_target"], ev, se_ev)
    action = "BUY" if direction > 0 else "SELL"
    return Stance(action=action, confidence=confidence,
                  reason=f"{action}: all gates passed ({regime}, R:R {rr:.2f})",
                  entry=entry, stop=float(stop), target=float(target), rr=float(rr),
                  size_units=float(size), risk_cash=float(risk_cash), gates=gates)


# --------------------------------------------------------------------------- #
# Historical feedback — walk the bars, apply the process, tally the outcomes.
# This is the "buena retroalimentación": how the WHOLE decision process behaves,
# not any single indicator. Costs and next-open fills included; no lookahead.
# --------------------------------------------------------------------------- #
def _edge_precondition(o, h, l, c, t, cfg: Config, cost_bps=1.0):
    """Validate the rule's edge on history STRICTLY BEFORE bar t (expanding
    window) — never on future bars. Returns (edge_ok, detail). Before there is
    enough history to close a trade, no edge is claimed and the process stays
    flat. This is the no-lookahead replacement for a single in-sample split.
    """
    # Direction must match the trend, so a SELL setup is validated on the SHORT
    # rule (c<ema, short P&L) — not a counter-trend long edge (backlog #6).
    direction = 1 if q.ols_trend(c[:t], cfg.r2_floor).slope > 0 else -1
    rule_sig = bt.rule_ema_trend(o[:t], h[:t], l[:t], c[:t], period=cfg.ema_period,
                                 direction=direction)
    net_is, cost = bt.simulate(rule_sig, o[:t], c[:t], cfg.horizon, cost_bps,
                               direction=direction)
    bs = bt.compute_stats(net_is, cost)
    # Return the direction the edge was validated for, so decide() can refuse it
    # if the slope flips between this bar and the trade bar (backlog #3).
    return (bs.verdict == "edge",
            f"expanding edge@{t} dir={direction} {bs.verdict} (exp {bs.expectancy_bps:+.1f}bps)",
            direction)


def _confidence(p_target, ev, se_ev):
    """Confidence tied to the actual edge — the barrier hit-probability and how
    far EV clears its Monte-Carlo noise (se_ev). Gate C already guarantees
    ev > se_ev, so 'low' means EV only marginally clears that noise; 'high' needs
    a clear directional hit-probability AND EV well clear of the noise."""
    margin = float("inf") if se_ev <= 0 else ev / se_ev
    if margin < 2.0:
        return "low"
    return "high" if p_target >= 0.55 else "medium"


def _ev_se(reward, risk, p_target, p_stop, n):
    """MC standard error of EV = p_target*reward - p_stop*risk, from the multinomial
    variance of the barrier hit-probabilities (includes the negative p_t/p_s
    covariance). Lets the EV gate require EV to clear zero by more than MC noise."""
    if n <= 0:
        return float("inf")
    var = (reward * reward * p_target * (1 - p_target)
           + risk * risk * p_stop * (1 - p_stop)
           + 2.0 * reward * risk * p_target * p_stop) / n
    return float(np.sqrt(var)) if var > 0 else 0.0


def _position_size(risk_cash, risk, entry, equity, max_leverage):
    """Units to trade, capped by a leverage limit. Fixed-fractional sizing alone
    (`risk_cash/risk`) blows up as the stop tightens (risk -> 0), demanding
    notional far beyond equity. Cap at `max_leverage * equity / entry`; when the
    cap binds, the ACTUAL cash at risk is size*risk. Returns (size, risk_cash)."""
    size = risk_cash / risk if risk > 0 else 0.0
    max_size = max_leverage * equity / entry if entry > 0 else size
    if size > max_size:
        return max_size, max_size * risk
    return size, risk_cash


def _resolve_exit(o, h, l, entry_i, horizon, direction, stop, target, n, slip=0.0):
    """Walk forward from entry_i and resolve the trade exit. A bar that GAPS
    through the stop fills at the (worse) OPEN, not the stop level. Stops are
    MARKET orders and slip against you by `slip` (a price fraction); targets are
    LIMIT orders and do not slip. Returns (exit_px, reason)."""
    for k in range(entry_i, min(entry_i + horizon, n)):
        if direction > 0:
            if l[k] <= stop:
                return min(float(o[k]), stop) * (1.0 - slip), "stop"
            if h[k] >= target:
                return target, "target"
        else:
            if h[k] >= stop:
                return max(float(o[k]), stop) * (1.0 + slip), "stop"
            if l[k] <= target:
                return target, "target"
    return float(o[min(entry_i + horizon, n - 1)]), "timeout"


def simulate_process(o, h, l, c, cfg: Config, cost_bps=1.0, refit=None, times=None):
    n = c.size
    warmup = max(cfg.ema_period, 30) + cfg.horizon
    # Expanding-window edge precondition, recomputed only from bars[:t] (never the
    # future). It is refreshed every `refit` bars rather than per-bar, bounding the
    # walk to O(n^2 / refit) instead of leaking a single in-sample-half decision
    # backwards onto earlier bars.
    if refit is None:
        refit = max(cfg.horizon, 10)
    edge_override = (False, "insufficient history")
    sigma_ref = None
    last_fit = -(10 ** 9)

    actions = {"BUY": 0, "SELL": 0, "NO-TRADE": 0}
    trades = []
    busy_until = -1
    for t in range(warmup, n - cfg.horizon):
        if t - last_fit >= refit:
            edge_override = _edge_precondition(o, h, l, c, t, cfg, cost_bps)
            # Throttle the (expensive multi-start) GARCH fit to the same cadence
            # instead of re-fitting every bar — O(n^2·starts) otherwise.
            ret_t = q.log_returns(c[:t + 1],
                                  times=(times[:t + 1] if times is not None else None))
            g = q.garch11_vol(ret_t)
            sigma_ref = g[0] if g else q.ewma_vol(ret_t)
            last_fit = t
        st = decide(o[:t + 1], h[:t + 1], l[:t + 1], c[:t + 1], cfg, edge_override,
                    times=(times[:t + 1] if times is not None else None),
                    sigma_override=sigma_ref)
        actions[st.action] += 1
        if st.action == "NO-TRADE" or t + 1 <= busy_until:
            continue
        # open a simulated position at next open; exit at stop/target/timeout
        entry_i = t + 1
        direction = 1 if st.action == "BUY" else -1
        entry_px = o[entry_i]
        exit_px, exit_reason = _resolve_exit(o, h, l, entry_i, cfg.horizon,
                                             direction, st.stop, st.target, n,
                                             slip=cfg.slip_frac)
        cost = 2.0 * cost_bps / 1e4
        r = direction * np.log(exit_px / entry_px) - cost
        trades.append((r, exit_reason))
        busy_until = min(entry_i + cfg.horizon, n)

    rets = np.array([r for r, _ in trades], dtype=float)
    reasons = {}
    for _, why in trades:
        reasons[why] = reasons.get(why, 0) + 1
    stats = bt.compute_stats(rets, 2.0 * cost_bps / 1e4) if rets.size else None
    return {
        "decisions": actions,
        "trades": int(rets.size),
        "exit_reasons": reasons,
        "expectancy_bps": float(rets.mean() * 1e4) if rets.size else 0.0,
        "win_rate": float(np.mean(rets > 0)) if rets.size else 0.0,
        "verdict": stats.verdict if stats else "no-trades",
        "ci95_bps": [stats.ci95_ret[0] * 1e4, stats.ci95_ret[1] * 1e4] if stats else None,
        "edge_precondition": edge_override[1],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--horizon", type=int, default=16)
    ap.add_argument("--min-rr", type=float, default=1.5)
    ap.add_argument("--simulate", action="store_true",
                    help="historical feedback: tally what the process would have done")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    payload = json.load(sys.stdin)
    bars = payload.get("bars") or payload.get("ohlcv") or []
    if not bars:
        raise SystemExit("no bars in input")
    o = np.array([b["open"] for b in bars], float)
    h = np.array([b["high"] for b in bars], float)
    l = np.array([b["low"] for b in bars], float)
    c = np.array([b["close"] for b in bars], float)
    t = np.array([b.get("time", i) for i, b in enumerate(bars)], float)
    cfg = Config(horizon=args.horizon, min_rr=args.min_rr)

    if args.simulate:
        fb = simulate_process(o, h, l, c, cfg, times=t)
        if args.json:
            print(json.dumps(fb, indent=2)); return
        _print_feedback(args, fb)
        return

    st = decide(o, h, l, c, cfg, times=t)
    if args.json:
        print(json.dumps(st.as_dict(), indent=2)); return
    _print_stance(args, st, float(c[-1]))


def _print_stance(args, st, last):
    W = 74
    print("=" * W)
    print(f" DECISION  {args.symbol} {args.tf}m   last={last:.2f}   (SIMULATION — no order placed)")
    print("=" * W)
    print(f"\n  >>> {st.action}  [{st.confidence}]   {st.reason}\n")
    for g in st.gates:
        mark = "PASS" if g["passed"] else "FAIL"
        print(f"  [{mark}] {g['name']:<14} {g['detail']}")
    if st.action != "NO-TRADE":
        print(f"\n  entry {st.entry:.2f}  stop {st.stop:.2f}  target {st.target:.2f}  "
              f"R:R {st.rr:.2f}")
        print(f"  size {st.size_units:.4f} units  (risk ${st.risk_cash:.2f} at {last:.2f})")
    else:
        print("\n  Flat is a position. No setup meets the bar; the honest move is to wait.")
    print("=" * W)
    print("Guardrail: this is a simulated recommendation. No broker was contacted and")
    print("no order was placed. Validate on Replay/paper before ever risking real money.")
    print("=" * W)


def _print_feedback(args, fb):
    W = 74
    print("=" * W)
    print(f" PROCESS FEEDBACK  {args.symbol} {args.tf}m   (walk-forward simulation)")
    print("=" * W)
    d = fb["decisions"]
    total = sum(d.values())
    print(f"\n  decisions: {total} bars evaluated")
    for k in ("NO-TRADE", "BUY", "SELL"):
        pct = 100 * d[k] / total if total else 0
        print(f"    {k:<10} {d[k]:>4}  ({pct:.1f}%)")
    print(f"\n  edge precondition: {fb['edge_precondition']}")
    print(f"  simulated trades : {fb['trades']}")
    if fb["trades"]:
        print(f"  exit reasons     : {fb['exit_reasons']}")
        print(f"  win rate         : {fb['win_rate']*100:.1f}%")
        print(f"  expectancy       : {fb['expectancy_bps']:+.2f} bps/trade (net)")
        ci = fb["ci95_bps"]
        print(f"  mean 95% CI      : [{ci[0]:+.2f}, {ci[1]:+.2f}] bps   verdict={fb['verdict']}")
    else:
        print("  The process stayed FLAT the whole window — no setup cleared all gates.")
        print("  That is the correct, honest outcome when there is no validated edge.")
    print("=" * W)


if __name__ == "__main__":
    main()
