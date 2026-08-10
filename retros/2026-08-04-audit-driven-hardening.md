<!-- review-status: pending -->

# Research-SDD Retro - audit-driven capability hardening

## Run

- Date: 2026-08-04
- Target: `tradingview-mcp`
- Mode: implementation (security/robustness hardening across the tool surface)
- Output: 6 focused commits on `feat/harden-dangerous-capabilities` (PR #429)

## What worked

- **A read-only audit subagent produced the work-list.** Instead of hardening tools ad hoc,
  one bounded agent swept `src/tools` + `src/core` and returned a PRIORITIZED backlog with
  `file:line` evidence and a concrete problem + fix per item. That backlog drove several
  independently reviewable commits and kept the parent context thin.
- **The audit stated what was clean, not only what was broken.** It confirmed there were NO
  injection vulnerabilities (every user-controlled value interpolated into page-evaluated JS
  is escaped). Recording the negative result stopped a speculative "sanitize everything" pass.
- **Each item shipped as its own work unit** (gate, confirmation guard, payload cap, input
  validation) with tests co-located and the offline suite kept green at every step. The safe
  suite grew from 74 to 164 tests without a single red intermediate state.
- **A failing test caught a real bug before merge.** `Number(null) === 0` / `Number('') === 0`
  meant a nullish index silently targeted item 0 and proceeded to live I/O, hanging the suite.
  The isolation guarantee (guards throw before any connection call) is what surfaced it.

## Method review

- **Audit findings are candidates, not mandates.** One backlog item ("gate `pine_save`") was
  deliberately NOT done: saving is the intended final step of an existing workflow with no
  casual-flag footgun, so gating it would degrade the primary use case for no proportional
  security gain. The higher-value change in the same module (cap the one unbounded payload)
  was done instead. Proportional judgment beat backlog completionism.
- **Protection mechanism was chosen by blast-radius × recoverability**, not one-size-fits-all:
  - irreversible + high-blast (arbitrary JS, remote-code self-update, position changes)
    -> process-level env capability gate with an exact acknowledgment string;
  - destructive but recoverable (bulk-delete alerts) -> per-call confirmation token, so the
    routine single-item path stays frictionless;
  - malformed input reaching a side effect -> validate-before-effect, no gate.
- **Scope discipline at the boundary.** A broad `_deps` dependency-injection refactor was left
  OUT of the hardening PR and recorded as a separate consistency follow-up, so a 6-commit
  security PR did not absorb an unrelated testability migration.

## Proposed kit deltas

- Add an **audit-then-backlog** step to the investigation loop for "harden/improve X" targets:
  a bounded read-only agent returns a prioritized, evidence-cited (`file:line`) backlog that
  becomes the work-list. Require it to report clean dimensions explicitly (a verified negative
  is a result), to prevent speculative work.
- Add a **protection-mechanism decision heuristic** (blast-radius × recoverability -> env gate
  / confirmation token / input validation) to the hardening guidance, and require the retro to
  record any backlog item deliberately skipped, with the rationale — so "not done" is a
  documented judgment, not an omission.

## Follow-up

- Human review to accept or dismiss the two proposed deltas.
- Related learning from the same session already captured in
  [2026-08-04-gitignore-anchoring.md](2026-08-04-gitignore-anchoring.md).
