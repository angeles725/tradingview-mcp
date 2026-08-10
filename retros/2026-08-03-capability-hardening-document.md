<!-- review-status: pending -->

# Research-SDD Retro - TradingView MCP capability-hardening document cycle

## Run

- Date: 2026-08-03
- Target: `tradingview-mcp`
- Mode: DOCUMENT / CAPTURE
- Output: B1-B3 plus `RUNBOOK-CAPABILITY-HARDENING.md`

## What worked

- The auto corpus heuristic selected the safe nested `corpus/` layout for an existing source repository.
- Offline source/tests and the preserved native-review transaction were sufficient; no TradingView/CDP interaction was needed.
- `verify-block.sh`, `verify-state.sh`, and `verify-sources.sh` all passed after citation and state reconciliation.

## Method review

The initial operator incorrectly blocked because the path was not yet registered. The current launcher already covers the correct behavior: an arbitrary path may become a NEW target when the user requests it, and bootstrap registers it. `PROMPT-LOOP.md` also already makes registration a bootstrap follow-up. This was a rule-compliance failure, not a missing kit rule.

## Proposed kit deltas

None. The kit already encodes the behavior that would have prevented the false blocker; duplicating it would add noise rather than improve the method.

## Follow-up

- Human review may mark this retro `dismissed` because it proposes no kit change, while retaining it as evidence that the run completed its self-retrospective.
