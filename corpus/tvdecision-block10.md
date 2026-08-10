# Block 10 - Closing the feedback loop: gated recurring collection via Claude Code hooks

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how recurring OHLCV collection was wired so it runs ONLY while both TradingView and Claude Code (this
> project) are in use - using Claude Code hooks rather than cron - and never consumes anything otherwise.
>
> Subject version: `analysis/collect-hook.sh` committed `742d08c` on branch `feat/quant-analysis-toolkit`
> (off `main` c05b8f5); wiring in local `.claude/settings.json`. Session 2026-08-05.
>
> Sources: `analysis/collect-hook.sh`, `.claude/settings.json` (local primary source). Preserved run:
> `sources/probes/collection-hook-session-2026-08-05.md`.
> Method: read-only citation of authored code plus a preserved in-session hook run. `[CERT]` marks a local
> `file:line`; `[CERT-live]` a preserved live measurement; `[CERT-hw]` a preserved in-session measurement;
> `[INFER]` an explicit deduction. METHODOLOGY/DESIGN block.
>
> Operational layer. Turns [Block 9]'s collector into an automatic, self-gating feed for [Block 8]'s
> feedback loop.

---

## 10.1 - Why hooks, not cron `[CERT]` / `[INFER]`

The requirement was to collect ONLY when TradingView AND Claude Code (this project) are in use, and to
consume nothing when Claude Code is closed. A Claude Code hook can only fire while Claude Code is running
in the project, so it matches that requirement natively (`analysis/collect-hook.sh:4`). Cron is a clock
that fires regardless, so it would need a heartbeat file to emulate "Claude is open" - strictly more
moving parts for the same effect. `[INFER]` The environment check confirmed cron was available but
deliberately left unused (`sources/probes/collection-hook-session-2026-08-05.md`).

## 10.2 - Two cheap gates before any work `[CERT]`

The hook exits doing nothing unless both gates pass. **Throttle**: it collects at most once per 30 minutes,
comparing a stamp file's mtime (`analysis/collect-hook.sh:39`) - a no-network check. **TV reachable**: a
short-timeout `curl` to the CDP endpoint (`analysis/collect-hook.sh:45`); a closed port fails fast and the
hook exits (`analysis/collect-hook.sh:46`). `[INFER]` Ordering throttle first means a normally-collecting
session skips straight out at the stamp check without even a network call.

## 10.3 - Detached so Claude is never delayed `[CERT]` / `[CERT-hw]`

When both gates pass the hook stamps the time and launches the pull with `nohup ... &`
(`analysis/collect-hook.sh:52`), returning immediately. Measured latency was ~0.018 s and the collection
ran in the background (`sources/probes/collection-hook-session-2026-08-05.md`) `[CERT-hw]`. The stamp is
written BEFORE the pull so a slow or failed collection still respects the throttle.

## 10.4 - Portable and wired at two events `[CERT]`

The script self-resolves the project from its own location (`analysis/collect-hook.sh:18`) and node/python
via PATH with fallbacks (`analysis/collect-hook.sh:25`), so it is not tied to a fixed machine path. It is
wired at both `SessionStart` and `Stop` in `.claude/settings.json` (`.claude/settings.json:1`): the first
collects once when the project opens, the second covers long sessions (throttled). The live log confirmed a
gated run appending a fresh bar to the store `[CERT-live]`
(`sources/probes/collection-hook-session-2026-08-05.md`).

## 10.5 - What this closes and the standing limit `[INFER]`

This makes [Block 9]'s collector automatic and self-gating, so history accumulates during normal use and
[Block 8]'s Gate B / feedback loop gain data over time without manual runs. It does not change the forward-
only limit: history grows from when collection starts; there is no backfill of bars the feed never
provided. The guardrails from [Block 5]/[Block 8] stand unchanged - more data sharpens estimates, it does
not make direction predictable.

## 10.6 - Connections

- **[Block 9]** - the collector this hook drives.
- **[Block 8]** - the decision engine whose feedback loop this feeds over time.
- **[Block 1]** - the WSL2 -> Windows CDP channel the TV-reachable gate probes.
