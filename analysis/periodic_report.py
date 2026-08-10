#!/usr/bin/env python3
"""
Render the month's periodic forecasts (corpus/periodic.jsonl) to a self-contained,
theme-aware HTML report: one card per forecast with the cone, cone-derived
stop-loss / take-profit, R:R and %-distances, plus an inline-SVG cone bar. No
external assets. Stdlib only.

Usage:
    <venv>/python analysis/periodic_report.py --out corpus/periodic-report.html
    <venv>/python analysis/periodic_report.py --symbol OANDA:XAUUSD
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import os

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "corpus", "periodic.jsonl")


def _read(path, symbol=None):
    if not os.path.exists(path):
        return []
    rows = []
    for ln in open(path):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if symbol is None or r.get("symbol") == symbol:
            rows.append(r)
    return rows


def _dt_utc(unix):
    return _dt.datetime.fromtimestamp(int(unix), _dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def _cone_svg(rec):
    """Horizontal cone bar: P5..P95 range with P50 (entry), SL, TP markers."""
    c = rec["cone"]; lv = rec["levels"]
    lo, hi = c["P5"], c["P95"]
    span = (hi - lo) or 1.0
    def x(v):
        return 8 + (v - lo) / span * 484
    def band(a, b, cls):
        return f'<rect x="{x(a):.1f}" y="20" width="{x(b)-x(a):.1f}" height="20" class="{cls}"/>'
    parts = [band(c["P5"], c["P95"], "b90"), band(c["P25"], c["P75"], "b50")]
    for v, cls, lbl in ((lv["stop_loss"], "sl", "SL"), (c["P50"], "mid", "entry"),
                        (lv["take_profit"], "tp", "TP")):
        parts.append(f'<line x1="{x(v):.1f}" y1="14" x2="{x(v):.1f}" y2="46" class="{cls}"/>')
        parts.append(f'<text x="{x(v):.1f}" y="60" class="tick">{lbl} {v:.0f}</text>')
    return f'<svg viewBox="0 0 500 70" class="cone">{"".join(parts)}</svg>'


def _card(rec):
    c = rec["cone"]; lv = rec["levels"]
    sym = html.escape(rec["symbol"]); per = rec["period"].upper()
    rev = rec.get("last_week_review")
    rev_html = ""
    if rev:
        rev_html = (f'<div class="rev">Revisión semana previa: entry {rev["S0"]:.2f}, '
                    f'cono [{rev["cone"]["P5"]:.0f}, {rev["cone"]["P95"]:.0f}] '
                    f'(madura {_dt_utc(rev["target_unix"])})</div>')
    side_cls = "long" if lv["side"] == "long" else "short"
    return f"""
    <article class="card">
      <header><span class="per {per.lower()}">{per}</span> <b>{sym}</b>
        <span class="tf">{html.escape(rec['tf'])} · h={rec['horizon_bars']} bars</span>
        <span class="side {side_cls}">{lv['side'].upper()}</span></header>
      <div class="meta">hecho {_dt_utc(rec['made_at_unix'])} · madura {_dt_utc(rec['target_unix'])} ·
        p_up {c['p_up']:.3f}</div>
      {_cone_svg(rec)}
      <div class="grid">
        <div><span>Entry</span><b>{lv['entry']:.2f}</b></div>
        <div class="k-sl"><span>Stop-Loss</span><b>{lv['stop_loss']:.2f}</b><i>-{lv['sl_pct']:.2f}%</i></div>
        <div class="k-tp"><span>Take-Profit</span><b>{lv['take_profit']:.2f}</b><i>+{lv['tp_pct']:.2f}%</i></div>
        <div><span>R:R</span><b>{lv['rr']:.2f}</b></div>
      </div>
      {rev_html}
      {_confluence_html(rec.get("confluence"))}
    </article>"""


def _confluence_html(conf):
    if not conf:
        return ""
    fb = " · ".join(f"{k}:{v:.0f}" for k, v in conf.get("fib_bull", {}).items())
    sc = conf.get("scenarios", {})
    return f"""<div class="conf">
      <div class="conf-h">Confluencia — {html.escape(conf.get('trend','?'))} · RSI {conf.get('rsi','?')}
        ({html.escape(conf.get('rsi_state','?'))}) · {html.escape(conf.get('accumulation','?'))} · POC {conf.get('poc','?')}</div>
      <div class="conf-fib">Fibo alcista: {fb}</div>
      <ul class="pan">
        <li class="p-bull"><b>Alcista:</b> {html.escape(sc.get('bull',''))}</li>
        <li class="p-base"><b>Base:</b> {html.escape(sc.get('base',''))}</li>
        <li class="p-bear"><b>Bajista:</b> {html.escape(sc.get('bear',''))}</li>
      </ul></div>"""


def render(rows, title="Pronósticos periódicos") -> str:
    order = {"month": 0, "week": 1}
    rows = sorted(rows, key=lambda r: (r.get("made_at_unix", 0), order.get(r.get("period"), 9)))
    cards = "\n".join(_card(r) for r in rows) or "<p>Sin pronósticos aún.</p>"
    n_m = sum(1 for r in rows if r.get("period") == "month")
    n_w = sum(1 for r in rows if r.get("period") == "week")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#f7f8fa;--fg:#1a1c1f;--muted:#6b7280;--card:#fff;--line:#e5e7eb;
  --b90:#c7d2fe;--b50:#818cf8;--sl:#ef5350;--tp:#26a69a;--mid:#111}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0f1115;--fg:#e6e8eb;
  --muted:#9aa4b2;--card:#171a21;--line:#242832;--b90:#2b3350;--b50:#4854b8;--mid:#e6e8eb}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:24px}}
h1{{font-size:20px;margin:0 0 4px}}.sub{{color:var(--muted);margin:0 0 20px;font-size:13px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 16px;max-width:640px}}
header{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.per{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:99px;color:#fff}}
.per.month{{background:#6366f1}}.per.week{{background:#0ea5e9}}
.tf{{color:var(--muted);font-size:12px}}.side{{margin-left:auto;font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px}}
.side.long{{background:rgba(38,166,154,.15);color:#26a69a}}.side.short{{background:rgba(239,83,80,.15);color:#ef5350}}
.meta{{color:var(--muted);font-size:12px;margin:6px 0 10px}}
.cone{{width:100%;height:70px}}.cone .b90{{fill:var(--b90)}}.cone .b50{{fill:var(--b50)}}
.cone .sl{{stroke:var(--sl);stroke-width:2}}.cone .tp{{stroke:var(--tp);stroke-width:2}}
.cone .mid{{stroke:var(--mid);stroke-width:2;stroke-dasharray:3 2}}
.cone .tick{{fill:var(--muted);font-size:10px;text-anchor:middle}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:10px}}
.grid div{{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px}}
.grid span{{display:block;color:var(--muted);font-size:11px}}.grid b{{font-size:16px}}
.grid i{{font-style:normal;font-size:12px;color:var(--muted)}}
.k-sl b{{color:var(--sl)}}.k-tp b{{color:var(--tp)}}
.rev{{margin-top:10px;font-size:12px;color:var(--muted);border-top:1px dashed var(--line);padding-top:8px}}
.conf{{margin-top:12px;border-top:1px solid var(--line);padding-top:10px;font-size:12px}}
.conf-h{{font-weight:600;margin-bottom:4px}}.conf-fib{{color:var(--muted);margin-bottom:6px}}
.pan{{margin:0;padding-left:0;list-style:none;display:grid;gap:4px}}
.pan li{{padding:4px 8px;border-radius:6px;background:var(--bg);border:1px solid var(--line)}}
.p-bull b{{color:var(--tp)}}.p-bear b{{color:var(--sl)}}.p-base b{{color:var(--muted)}}
.note{{max-width:640px;color:var(--muted);font-size:12px;margin-top:8px}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="sub">{n_m} mensual(es) · {n_w} semanal(es) · SL/TP derivados del cono (P5/P95)</p>
{cards}
<p class="note">Los niveles salen del cono probabilístico (bandas honestas), no de una
predicción de dirección: p_up ≈ 0.50. El Stop-Loss/Take-Profit son gestión de riesgo,
no una señal de compra/venta.</p>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(STORE), "periodic-report.html"))
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--title", default="Pronósticos periódicos — mes")
    args = ap.parse_args()
    rows = _read(STORE, args.symbol)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write(render(rows, args.title))
    print(f"report: {len(rows)} forecast(s) -> {args.out}")


if __name__ == "__main__":
    main()
