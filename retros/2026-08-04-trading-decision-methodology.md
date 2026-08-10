<!-- review-status: pending -->

# Research-SDD Retro - trading analysis & decision methodology (DOCUMENT cycle)

## Run

- Date: 2026-08-04
- Target: `tradingview-mcp`
- Mode: DOCUMENT (CAPTURE, outline-driven; no gap discovery)
- Focus: `tvdecision` (distinct from the existing `tradingview-` capability-hardening focus)
- Output: 3 cited blocks (`tvdecision-block1..3.md`), a dedicated index (`INDEX-DECISIONS.md`),
  the primary deliverable (`DECISION-PLAYBOOK.md`), one preserved session receipt
  (`sources/probes/decision-methodology-session-2026-08-04.md`), and a second focus section appended
  to the shared `RESEARCH-STATE.md`. All three verify gates pass (verify-block x3, verify-state,
  verify-sources - all exit 0).

## What worked

- **A single preserved session receipt anchored every `[CERT-hw]` claim.** The WSL2->Windows CDP
  topology, the "MCP not loaded, read via CLI + PNG" channel fact, and the measured ~300-bar live cap
  all resolve to one `sources/probes/` file, so verify-block's probe check passes and the claims are
  reproducible rather than transcript-only.
- **The subject/method split kept markers honest.** CLI-surface facts (command names, `MAX_OHLCV_BARS`,
  the Replay commands) are `[CERT]` to `../src/...:line` and all resolved; the analysis behaviour
  (regression trend, zero-drift Monte Carlo range, sample-size caveat, backtest traps) is `[INFER]`
  because the method scripts are ephemeral scratchpad, not preserved primary source. Declaring B2/B3 as
  METHODOLOGY/DESIGN blocks made the high `[INFER]`/`[CERT]` ratio read as expected, not as exhaustion.
- **The deliverable is a checklist, not prose.** `DECISION-PLAYBOOK.md` is copy-paste command blocks in
  execution order (is-it-live -> read in 6 commands -> assess -> guardrails -> Replay), which is the
  actual speed lever the run existed to produce.
- **The non-negotiable guardrail survived into every layer.** "Range with a probability, never a point;
  no method predicts direction; validate by honest backtest; risk management first; the tool cannot
  prove broker isolation" appears in B2, B3, and the playbook - not just once.

## Method review

- **Second focus on a legacy single-state corpus.** The corpus already had one focus under the legacy
  `RESEARCH-STATE.md` (empty focus prefix -> `verify-state` counts blocks corpus-wide). Adding the
  `tvdecision-` focus meant the envelope had to move to the GLOBAL block count (3 -> 6) and the canonical
  coverage metric had to become one number (6 / 6), while each focus keeps its own INDEX. This satisfied
  all gates, but it merges two focuses' counts into one envelope rather than tracking them separately.
- **No fabrication under the DOCUMENT contract.** No script was re-run this session, so no result value
  was cited; only hard-coded script parameters (cost, horizon, seed, bar caps) and preserved measured
  bar counts (300 / 300 / 200) were used, the latter re-counted from the preserved JSON before citing.
- **READ-ONLY held.** No CDP/broker interaction, no `src/`/`tests/` edit, no commit.

## Proposed kit deltas

- **DOCUMENT-cycle guidance for adding a NEW focus to an existing SINGLE-`RESEARCH-STATE.md` corpus.**
  METHODOLOGY §16 describes per-focus `RESEARCH-STATE-<focus>.md` with a prefix that mirrors the suffix,
  but §20 (DOCUMENT cycle) is silent on the common case of appending a second focus to a corpus that
  already uses one legacy `RESEARCH-STATE.md`. The operator must currently DEDUCE that the choice is
  either (a) bump the shared envelope to the corpus-wide block count and keep one canonical coverage
  metric, or (b) introduce a `FOCUSES.md` so `focus-prefix.sh` gives each focus its own count. A short
  §20 note stating this fork (and that option (a) requires ONE canonical coverage-metric line to avoid
  `verify-state` CHECK 3) would remove the guesswork. Priority: low-medium (verifiable-today; the gates
  already enforce the invariant, they just do not teach the choice).

## Follow-up

- Human review to accept or dismiss the proposed §20 delta above.
- If the `tvdecision` focus grows, consider migrating to a dedicated `RESEARCH-STATE-tvdecision.md` +
  `FOCUSES.md` so per-focus coverage is tracked independently of the capability-hardening focus.
