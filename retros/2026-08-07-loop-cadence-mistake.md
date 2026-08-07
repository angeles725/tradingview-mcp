# Retro — self-paced loop cadence mistake (2026-08-07)

## What happened
Running `/research-sdd` under `/loop` (self-paced), after finishing iteration 1 I scheduled the
next iteration at **1500s (~25 min)**. When challenged, I justified it as an "idle window for user
consent before touching trading logic." The user correctly pointed out this contradicts the loop rule.

## Why it was wrong
The research-sdd launcher / PROMPT-LOOP RESCHEDULE CADENCE rule is explicit:
> self-paced: **reschedule at the ~60s floor until STOP fires**.

The next iteration was **my own work** (implement fix #6) with **no external signal to wait on**.
There was nothing to poll and nothing to wait for, so a long fallback delay was pure stall. The
generic `/loop` guidance ("idle ticks 1200–1800s") applies to *idle waiting*, not to a research-sdd
run that has queued work ready to execute — the research-sdd cadence overrides it.

## Root cause
I conflated two distinct concerns:
1. **Cadence** (how soon to resume) — governed by the ~60s floor when work is ready.
2. **Consent** (whether to edit live trading logic autonomously) — a separate decision.

I used a slow cadence as a proxy for a consent checkpoint. Wrong lever: if consent is needed, ASK or
surface it and keep the loop tight — do not silently delay the whole loop.

## Correct behavior
- When the next research-sdd iteration is queued work with no external dependency: **reschedule at
  the ~60s floor**, or just execute it in the same turn.
- Reserve long fallback delays (1200s+) ONLY for genuine external waits (CI, remote state, a Monitor
  as primary wake signal).
- If autonomy over a sensitive edit is the concern, handle it as an explicit consent surface, not as
  a cadence delay.

## Applied
Immediately reprioritized: executed the queued fix (#6, SELL-rule mirror) in-turn under strict TDD
(red → green) instead of waiting 25 min.
