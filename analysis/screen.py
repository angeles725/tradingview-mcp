#!/usr/bin/env python3
"""
Multi-symbol / multi-timeframe screener — drive the live chart over CDP and run
the gated decision engine on each (symbol, timeframe), with a timeframe ladder
to step the chart up/down.

SAFETY: like decide.py, this NEVER places an order. It only sets the chart
symbol/timeframe, READS bars over CDP (via `node src/cli/index.js`), and prints
a recommendation. Paper only.

Why this exists: screening for momentum means sweeping the SAME symbols across
timeframes (15m microstructure is mean-reverting; a real trend edge, if any,
shows up at 1h/4h/D where VR>1). Doing that by hand is slow and error-prone
(the feed lags a few seconds after each switch, and an invalid symbol wedges the
chart). This automates the switch -> wait-for-feed -> decide loop.

Usage (run under the scipy venv so numpy/scipy are importable):
    VENV=~/.local/share/research-sdd-tools/venv/bin/python3

    # sweep symbols x timeframes through the decision engine
    $VENV analysis/screen.py \
        --symbols OANDA:XAUUSD,OANDA:EURUSD,OANDA:SPX500USD \
        --tfs 15,60,240

    # add the walk-forward feedback (expectancy) per row (slower)
    $VENV analysis/screen.py --symbols OANDA:XAUUSD --tfs 60,240 --simulate

    # re-run every 5 minutes (automation / monitoring)
    $VENV analysis/screen.py --symbols OANDA:XAUUSD --tfs 60 --every 300

    # step the CURRENT chart timeframe along the ladder (1,5,15,30,60,120,240,D,W)
    $VENV analysis/screen.py tf --up
    $VENV analysis/screen.py tf --down
    $VENV analysis/screen.py tf --set 240
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

import numpy as np

# decide.py uses `import quant`/`import backtest`, so its own dir must be importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import decide as dec                                     # noqa: E402
import forecast as fc                                    # noqa: E402

REPO_ROOT = os.path.dirname(_HERE)
CLI = ["node", "src/cli/index.js"]

# TradingView resolution ladder, fine -> coarse. Stepping is clamped at the ends.
# Values match what `state` reads BACK (intraday minutes as-is; daily+ as 1D/1W).
TF_LADDER = ["1", "5", "15", "30", "60", "120", "240", "1D", "1W"]
TF_LABEL = {"60": "1h", "120": "2h", "240": "4h", "1D": "1D", "1W": "1W"}


def _tf_label(tf: str) -> str:
    return TF_LABEL.get(tf, f"{tf}m" if tf.isdigit() else tf)


# --------------------------------------------------------------------------- #
# CDP plumbing — everything goes through the repo's node CLI (port 9222).
# --------------------------------------------------------------------------- #
def run_cli(*args: str, timeout: float = 30.0) -> dict | None:
    """Run `node src/cli/index.js <args>` from the repo root and parse its JSON.
    Returns the parsed object, or None on failure/non-JSON."""
    try:
        p = subprocess.run(CLI + list(args), cwd=REPO_ROOT, capture_output=True,
                           text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    out = p.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def current_state() -> tuple[str, str]:
    """(symbol, resolution) of the live chart, or ('', '')."""
    st = run_cli("state")
    if not st or not st.get("success", True) and "symbol" not in st:
        return "", ""
    return st.get("symbol", ""), str(st.get("resolution", ""))


def wait_feed(symbol: str, tf: str, min_bars: int, max_wait: float = 16.0) -> list | None:
    """After a symbol/timeframe switch the feed lags a few seconds. Poll until the
    chart reports THIS symbol+resolution AND ohlcv returns >= min_bars, else None."""
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        time.sleep(1.0)
        sym, res = current_state()
        if sym != symbol or res != str(tf):
            continue
        data = run_cli("ohlcv", "--count", "300", "--json")
        if data and data.get("success") and len(data.get("bars", [])) >= min_bars:
            return data["bars"]
    return None


def set_chart(symbol: str, tf: str) -> None:
    run_cli("symbol", symbol)
    run_cli("timeframe", str(tf))


# --------------------------------------------------------------------------- #
# Decision — call the engine directly on the pulled bars (no second process).
# --------------------------------------------------------------------------- #
def _arrays(bars: list) -> tuple:
    o = np.array([b["open"] for b in bars], float)
    h = np.array([b["high"] for b in bars], float)
    l = np.array([b["low"] for b in bars], float)
    c = np.array([b["close"] for b in bars], float)
    t = np.array([b.get("time", i) for i, b in enumerate(bars)], float)
    return o, h, l, c, t


def _gate_a(stance) -> str:
    for g in stance.gates:
        if str(g.get("name", "")).startswith("A_"):
            return g.get("detail", "")
    # Gate A passed: report the first failing gate instead, or the headline.
    for g in stance.gates:
        if not g.get("passed"):
            return g.get("detail", "")
    return stance.reason


_VR_RE = re.compile(r"VR(\d+)=([-\d.]+)\s*\(z=([-\d.]+)\)")
_R2_RE = re.compile(r"R\^2=([-\d.]+)")
_REG_RE = re.compile(r"regime=([\w-]+)")


def _parse_momentum(gate_a: str, vr_z_floor: float) -> dict:
    """Pull the momentum verdict out of the Gate A detail string so the deciding
    number (VR>1 with a significant z) is surfaced, not buried in truncated text.
    A missing field stays None rather than guessing."""
    vr = z = r2 = None
    regime = ""
    m = _VR_RE.search(gate_a)
    if m:
        vr, z = float(m.group(2)), float(m.group(3))
    mr = _R2_RE.search(gate_a)
    if mr:
        r2 = float(mr.group(1))
    mg = _REG_RE.search(gate_a)
    if mg:
        regime = mg.group(1)
    # Momentum edge = VR>1 AND the Lo-MacKinlay z clears the significance floor.
    is_mom = vr is not None and z is not None and vr > 1.0 and z >= vr_z_floor
    return {"vr": vr, "vr_z": z, "r2": r2, "regime": regime, "momentum": is_mom}


def decide_on(bars: list, horizon: int, min_rr: float, simulate: bool) -> dict:
    o, h, l, c, t = _arrays(bars)
    cfg = dec.Config(horizon=horizon, min_rr=min_rr)
    st = dec.decide(o, h, l, c, cfg, times=t)
    gate_a = _gate_a(st)
    row = {
        "action": st.action,
        "confidence": st.confidence,
        "rr": st.rr,
        "entry": st.entry,
        "stop": st.stop,
        "target": st.target,
        "gate_a": gate_a,
        "momentum": _parse_momentum(gate_a, cfg.vr_z),
        "reason": st.reason,
    }
    if simulate:
        fb = dec.simulate_process(o, h, l, c, cfg, times=t)
        row["feedback"] = {
            "trades": fb["trades"],
            "expectancy_bps": round(fb["expectancy_bps"], 1),
            "win_rate": round(fb["win_rate"], 2),
            "verdict": fb["verdict"],
        }
    return row


def record_forecast(bars: list, symbol: str, tf: str, horizon: int, log: str) -> str:
    """Log a cone forecast for (symbol, tf) so every screen grows the calibration
    dataset. Runs analyze.py --json (which emits the monte_carlo cones + the
    self-contained last_bar_unix/bar_step_sec), builds a record, and appends it.
    Returns a short status string; never raises into the sweep."""
    try:
        p = subprocess.run(
            [sys.executable, os.path.join(_HERE, "analyze.py"),
             "--symbol", symbol, "--tf", str(tf), "--json"],
            input=json.dumps({"bars": bars}), cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=60)
        report = json.loads(p.stdout)
        rec = fc.build_record(report)
        with fc._lock(log):
            fc.append_log(log, rec)
        return f"forecast logged (target_unix={rec['target_unix']})"
    except Exception as e:                               # analyze/parse/lock failure
        return f"forecast NOT logged ({type(e).__name__})"


# --------------------------------------------------------------------------- #
# Screen — sweep symbols x timeframes, restoring the original chart at the end.
# --------------------------------------------------------------------------- #
def screen(symbols: list, tfs: list, horizon: int, min_rr: float,
           simulate: bool, min_bars: int, as_json: bool,
           record: bool = False, log: str = None) -> list:
    log = log or fc.DEFAULT_LOG
    results = []
    for tf in tfs:
        rows = []
        for sym in symbols:
            set_chart(sym, tf)
            bars = wait_feed(sym, tf, min_bars)
            if bars is None:
                rows.append({"symbol": sym, "tf": tf, "error": "feed not ready"})
                continue
            row = decide_on(bars, horizon, min_rr, simulate)
            row.update({"symbol": sym, "tf": tf, "bars": len(bars)})
            if record:
                row["recorded"] = record_forecast(bars, sym, tf, horizon, log)
            rows.append(row)
        results.append({"tf": tf, "rows": rows})
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        _print_table(results, simulate, record)
    return results


def _mom_cell(mom: dict) -> str:
    """Compact momentum verdict: the deciding VR>1?/z, flagged when it's a real
    momentum edge (VR>1 and a significant z). '·' means no momentum."""
    if not mom or mom.get("vr") is None:
        return f"{'·':<21}"
    flag = "MOM^" if mom.get("momentum") else " -  "
    return f"{flag} VR={mom['vr']:.2f} z={mom['vr_z']:+.2f}".ljust(21)


def _print_table(results: list, simulate: bool, record: bool = False) -> None:
    for block in results:
        tf = block["tf"]
        print(f"\n################  TIMEFRAME {_tf_label(tf)} ({tf})  ################")
        head = f"{'SYMBOL':<12} {'ACTION':<9} {'R:R':<6} {'CONF':<6} {'MOMENTUM':<21} "
        if simulate:
            head += f"{'EXP.bps':<9} {'VERDICT':<11}"
        head += "regime / trend"
        print(head)
        print("-" * 106)
        for r in block["rows"]:
            sym = r["symbol"].replace("OANDA:", "")
            if "error" in r:
                print(f"{sym:<12} {'ERR':<9} {'-':<6} {'-':<6} {r['error']}")
                continue
            rr = f"{r['rr']:.2f}" if isinstance(r.get("rr"), (int, float)) else "-"
            mom = r.get("momentum", {})
            line = (f"{sym:<12} {r['action']:<9} {rr:<6} {str(r['confidence']):<6} "
                    f"{_mom_cell(mom)} ")
            if simulate:
                fb = r.get("feedback", {})
                line += f"{str(fb.get('expectancy_bps','-')):<9} {str(fb.get('verdict','-')):<11}"
            reg = mom.get("regime", "") if mom else ""
            r2 = mom.get("r2") if mom else None
            line += f"{reg}" + (f" R^2={r2:.2f}" if r2 is not None else "")
            if record and r.get("recorded"):
                line += f"  [{r['recorded']}]"
            print(line)


# --------------------------------------------------------------------------- #
# Timeframe ladder — step the current chart up/down or set it directly.
# --------------------------------------------------------------------------- #
def tf_cmd(up: bool, down: bool, set_to: str | None) -> None:
    sym, res = current_state()
    if not sym:
        raise SystemExit("no live chart (is TradingView up with CDP on 9222?)")
    if set_to is not None:
        target = set_to
    else:
        if res not in TF_LADDER:
            raise SystemExit(f"current resolution {res!r} is not on the ladder {TF_LADDER}")
        i = TF_LADDER.index(res)
        j = min(i + 1, len(TF_LADDER) - 1) if up else max(i - 1, 0)
        target = TF_LADDER[j]
    run_cli("timeframe", str(target))
    time.sleep(1.5)
    _, new_res = current_state()
    print(f"timeframe {_tf_label(res)} ({res}) -> {_tf_label(new_res)} ({new_res})")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    tf = sub.add_parser("tf", help="step the current chart timeframe up/down the ladder")
    g = tf.add_mutually_exclusive_group(required=True)
    g.add_argument("--up", action="store_true", help="one step coarser (e.g. 60 -> 120)")
    g.add_argument("--down", action="store_true", help="one step finer (e.g. 240 -> 120)")
    g.add_argument("--set", dest="set_to", metavar="RES", help="set directly (e.g. 240, D)")

    # default (no subcommand) = screen
    ap.add_argument("--symbols", default="OANDA:XAUUSD",
                    help="comma-separated symbols (default: OANDA:XAUUSD)")
    ap.add_argument("--tfs", default="15,60,240",
                    help="comma-separated timeframes (default: 15,60,240)")
    ap.add_argument("--horizon", type=int, default=16, help="forward bars for the cone/trade")
    ap.add_argument("--min-rr", type=float, default=1.5)
    ap.add_argument("--simulate", action="store_true",
                    help="also run the walk-forward feedback (expectancy) per row")
    ap.add_argument("--record", action="store_true",
                    help="log a cone forecast per row to grow the calibration dataset")
    ap.add_argument("--log", default=fc.DEFAULT_LOG,
                    help="forecast log for --record (default: corpus/forecasts.jsonl)")
    ap.add_argument("--min-bars", type=int, default=200,
                    help="minimum bars required before deciding (default 200)")
    ap.add_argument("--every", type=int, default=0, metavar="SECONDS",
                    help="repeat the screen every N seconds (0 = once)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--no-restore", action="store_true",
                    help="do not restore the original chart symbol/timeframe at the end")
    args = ap.parse_args()

    if args.cmd == "tf":
        tf_cmd(args.up, args.down, args.set_to)
        return

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    tfs = [s.strip() for s in args.tfs.split(",") if s.strip()]
    orig = current_state()
    try:
        while True:
            if args.every:
                print(f"\n===== screen @ {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
            screen(symbols, tfs, args.horizon, args.min_rr,
                   args.simulate, args.min_bars, args.json,
                   record=args.record, log=args.log)
            if not args.every:
                break
            time.sleep(args.every)
    except KeyboardInterrupt:
        pass
    finally:
        if not args.no_restore and orig[0]:
            set_chart(orig[0], orig[1])


if __name__ == "__main__":
    main()
