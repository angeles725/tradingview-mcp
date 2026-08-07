#!/usr/bin/env python3
"""
Honest backtest engine. Turns a candidate RULE into a validated edge — or
refutes it — over TradingView OHLCV read from the tv CLI on stdin.

It is built to resist the three ways a backtest lies (Block 3):
  1. SAMPLE — too few trades. n<30 is flagged 'thin-sample'; the mean edge
     carries a bootstrap 95% CI, and an edge whose CI includes 0 is NOT real.
  2. OVERFIT — a rule tuned to the past. An in-sample / out-of-sample split
     reports both; an edge that survives only in-sample is overfit.
  3. COSTS — the silent killer. Transaction cost is subtracted per side; the
     report shows gross vs net so you see exactly how much cost eats.

No lookahead: a signal on bar t is filled at the OPEN of bar t+1 and exited at
the open of bar t+1+hold. The rule never sees the bar it trades into.

Usage:
    node src/cli/index.js ohlcv --count 300 \
      | <venv>/python analysis/backtest.py --rule ema_trend --hold 8 --cost-bps 1.0
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict

import numpy as np

import quant as q


# --------------------------------------------------------------------------- #
# Rules — each returns a boolean signal array aligned to bars, using ONLY
# information known at the close of bar t (no lookahead).
# --------------------------------------------------------------------------- #
def rule_ema_trend(o, h, l, c, period=20, direction=1):
    """Trend-following rule, mirrored to the trade direction.

    Long (direction >= 0): close above its EMA. Short (direction < 0): close
    BELOW its EMA. The condition must follow the direction — testing a long
    signal for a short setup measures a counter-trend edge that does not exist.
    """
    e = q.ema(c, period)
    sig = (c > e) if direction >= 0 else (c < e)
    sig[np.isnan(e)] = False
    return sig


def rule_rsi_oversold(o, h, l, c, period=14, level=30):
    """Long when RSI dips below `level` — mean-reversion candidate."""
    r = q.rsi_wilder(c, period)
    sig = r < level
    sig[np.isnan(r)] = False
    return sig


def rule_three_up(o, h, l, c, **_):
    """Long after three consecutive up bars — momentum candidate."""
    up = np.zeros(c.size, dtype=bool)
    up[1:] = np.diff(c) > 0
    sig = np.zeros(c.size, dtype=bool)
    for t in range(2, c.size):
        sig[t] = up[t] and up[t - 1] and up[t - 2]
    return sig


RULES = {
    "ema_trend": rule_ema_trend,
    "rsi_oversold": rule_rsi_oversold,
    "three_up": rule_three_up,
}


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
@dataclass
class BTStats:
    n: int
    win_rate: float
    expectancy_ret: float      # mean net log return per trade
    expectancy_bps: float      # same, in basis points
    ci95_ret: tuple            # bootstrap CI on the mean net return
    gross_ret: float           # mean return BEFORE costs
    cost_ret: float            # per-trade round-trip cost (return units)
    profit_factor: float       # sum wins / sum |losses|
    t_stat: float              # mean / (std/sqrt(n)) — parametric sanity
    verdict: str               # 'edge' | 'no-edge' | 'thin-sample'

    def as_dict(self):
        return asdict(self)


def simulate(signal, o, c, hold, cost_bps_per_side, direction=1, overlap=False,
             return_entries=False):
    """
    Fill each signal at next-bar OPEN, exit `hold` bars later at the OPEN.
    Returns per-trade NET log returns (round-trip cost subtracted).

    overlap=False (DEFAULT): NON-overlapping trades — once in a trade, ignore
    further signals until it closes. This models a single-position portfolio AND
    keeps the trades statistically independent, so the bootstrap CI and t-stat
    are honest. overlap=True gives the raw signal-conditional view (every signal
    counted), whose overlapping trades are autocorrelated and inflate
    significance — use it only to read average forward return, never for a CI.
    """
    o = np.asarray(o, dtype=float)
    n = o.size
    cost = 2.0 * cost_bps_per_side / 1e4   # round-trip, in return units
    trades = []
    entries = []
    busy_until = -1                        # index up to which a position is open
    for t in np.flatnonzero(signal):
        entry_i = t + 1
        exit_i = t + 1 + hold
        if exit_i >= n:
            continue                       # not enough forward bars — drop, don't peek
        if not overlap and entry_i <= busy_until:
            continue                       # already in a trade — skip this signal
        gross = direction * np.log(o[exit_i] / o[entry_i])
        trades.append(gross - cost)
        entries.append(entry_i)
        busy_until = exit_i
    net = np.array(trades, dtype=float)
    if return_entries:
        return net, np.array(entries, dtype=int), cost
    return net, cost


def compute_stats(net, cost=0.0, min_n=30) -> BTStats:
    n = net.size
    if n == 0:
        return BTStats(0, 0.0, 0.0, 0.0, (float("nan"),) * 2, 0.0, cost,
                       0.0, 0.0, "thin-sample")
    wins = net[net > 0]
    losses = net[net < 0]
    win_rate = wins.size / n
    mean = float(net.mean())
    gross = mean + cost
    # Serial-dependence-honest CI: even non-overlapping trades cluster by regime,
    # so the i.i.d. bootstrap under-covers. Judge the edge on the (wider) block CI.
    ci = q.bootstrap_mean_ci_block(net)
    pf = float(wins.sum() / -losses.sum()) if losses.size and losses.sum() < 0 else float("inf")
    sd = net.std(ddof=1) if n > 1 else 0.0
    t_stat = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
    if n < min_n:
        verdict = "thin-sample"
    elif ci[0] > 0:                         # whole CI above zero -> real net edge
        verdict = "edge"
    else:
        verdict = "no-edge"
    return BTStats(n, win_rate, mean, mean * 1e4, ci, gross, cost, pf,
                   float(t_stat), verdict)


def walk_forward(signal, o, c, hold, cost, split=0.6, overlap=False):
    """Split the timeline; report in-sample vs out-of-sample expectancy."""
    n = o.size
    cut = int(n * split)
    is_sig = signal.copy(); is_sig[cut:] = False
    oos_sig = signal.copy(); oos_sig[:cut] = False
    cost_bps = cost / 2 * 1e4
    is_net, _ = simulate(is_sig, o, c, hold, cost_bps, overlap=overlap)
    oos_net, _ = simulate(oos_sig, o, c, hold, cost_bps, overlap=overlap)
    return compute_stats(is_net, cost), compute_stats(oos_net, cost)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", choices=list(RULES), default="ema_trend")
    ap.add_argument("--hold", type=int, default=8, help="bars held per trade")
    ap.add_argument("--cost-bps", type=float, default=1.0,
                    help="transaction cost per side, in basis points of price")
    ap.add_argument("--period", type=int, default=20, help="rule lookback (EMA/RSI)")
    ap.add_argument("--overlap", action="store_true",
                    help="count every signal (autocorrelated; inflates CI) instead "
                         "of non-overlapping independent trades (default)")
    ap.add_argument("--symbol", default="?")
    ap.add_argument("--tf", default="15")
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

    signal = RULES[args.rule](o, h, l, c, period=args.period)
    net, entries, cost = simulate(signal, o, c, args.hold, args.cost_bps,
                                  overlap=args.overlap, return_entries=True)
    stats = compute_stats(net, cost)
    is_stats, oos_stats = walk_forward(signal, o, c, args.hold, cost, overlap=args.overlap)

    # Serial-dependence-honest CI (trades cluster by regime even when non-overlapping)
    block_ci = q.bootstrap_mean_ci_block(net) if net.size else (float("nan"),) * 2

    # Per-regime expectancy — is the edge only inside a trend?
    regimes = q.classify_regime(c, window=20)
    by_regime = {}
    for lbl in ("trend-up", "trend-down", "chop"):
        sel = net[np.array([str(regimes[i]) == lbl for i in entries], dtype=bool)] \
            if net.size else np.array([])
        by_regime[lbl] = {
            "n": int(sel.size),
            "expectancy_bps": float(sel.mean() * 1e4) if sel.size else 0.0,
        }

    report = {
        "symbol": args.symbol, "timeframe": args.tf, "rule": args.rule,
        "hold_bars": args.hold, "cost_bps_per_side": args.cost_bps,
        "mode": "overlapping" if args.overlap else "non-overlapping",
        "signals_fired": int(signal.sum()), "independent_trades": int(stats.n),
        "bars": int(c.size),
        "full": stats.as_dict(),
        "block_bootstrap_ci95_bps": [block_ci[0] * 1e4, block_ci[1] * 1e4],
        "by_regime": by_regime,
        "in_sample": is_stats.as_dict(), "out_of_sample": oos_stats.as_dict(),
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return
    _print(report)


def _print(r):
    W = 74
    print("=" * W)
    print(f" HONEST BACKTEST  {r['symbol']} {r['timeframe']}m   rule={r['rule']}  "
          f"hold={r['hold_bars']}  cost={r['cost_bps_per_side']}bps/side")
    print(f" {r['signals_fired']} signals -> {r['independent_trades']} {r['mode']} trades "
          f"over {r['bars']} bars")
    print("=" * W)

    def block(title, s):
        print(f"\n{title}   [{s['verdict'].upper()}]")
        print(f"  trades      : {s['n']}    win rate: {s['win_rate']*100:.1f}%")
        print(f"  expectancy  : {s['expectancy_bps']:+.2f} bps/trade (NET)   "
              f"gross {s['gross_ret']*1e4:+.2f} - cost {s['cost_ret']*1e4:.2f}")
        print(f"  mean 95% CI : [{s['ci95_ret'][0]*1e4:+.2f}, {s['ci95_ret'][1]*1e4:+.2f}] bps   "
              f"t={s['t_stat']:+.2f}")
        print(f"  profit factor: {s['profit_factor']:.2f}")

    block("FULL SAMPLE", r["full"])
    bci = r["block_bootstrap_ci95_bps"]
    print(f"  block-boot CI: [{bci[0]:+.2f}, {bci[1]:+.2f}] bps  "
          f"(serial-dependence honest; wider = trades cluster by regime)")

    print("\nBY REGIME (entry-bar regime; is the edge only inside a trend?)")
    for lbl, d in r["by_regime"].items():
        print(f"  {lbl:<12} n={d['n']:>3}   expectancy {d['expectancy_bps']:+.2f} bps")

    block("IN-SAMPLE (first 60%)", r["in_sample"])
    block("OUT-OF-SAMPLE (last 40%)", r["out_of_sample"])

    fs, oos = r["full"], r["out_of_sample"]
    print("\nVERDICT")
    if fs["verdict"] == "thin-sample":
        print("  Too few trades to conclude anything. Need ~30+; collect more or widen the rule.")
    elif fs["verdict"] == "edge" and oos["verdict"] == "edge":
        print("  Net edge survives costs AND out-of-sample. Worth Replay practice — still")
        print("  size with risk management; a backtest is necessary, not sufficient.")
    elif fs["verdict"] == "edge" and oos["verdict"] != "edge":
        print("  Edge full-sample but NOT out-of-sample -> likely OVERFIT. Do not trade it.")
    else:
        print("  No net edge after costs. The rule does not beat the baseline. Discard it.")
    print("=" * W)
    print("Reminder: this measures a RULE, not the future. Costs + sample + overfit are")
    print("the three liars; risk management decides survival regardless of the edge.")
    print("=" * W)


if __name__ == "__main__":
    main()
