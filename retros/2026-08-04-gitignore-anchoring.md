<!-- review-status: pending -->

# Research-SDD Retro - gitignore anchoring for nested investigation artifacts

## Run

- Date: 2026-08-04
- Target: `tradingview-mcp`
- Mode: DOCUMENT / CAPTURE (follow-up)
- Context: excluding `corpus/`, `retros/`, and `tools/` from the product git history

## What happened

When integrating the nested Research-SDD corpus into an existing source repository, the
investigation artifact directories (`corpus/`, `retros/`, `tools/`) had to be added to the
target's `.gitignore` so they stop appearing as untracked product files.

Writing the entries unanchored (`tools/`) silently matched a same-named subdirectory of the
product tree (`src/tools/`) and blocked staging of real source files. Git directory patterns
without a leading slash match at ANY depth, so `tools/` == `**/tools/`. The fix was to
root-anchor every entry: `/corpus/`, `/retros/`, `/tools/`.

## Method review

The nested corpus layout deliberately places these directories at the repository root. Any
ignore rule the kit emits (or instructs the operator to emit) for them must be root-anchored,
because generic source repos commonly contain `src/tools/`, `lib/tools/`, `tests/corpus/`, and
similar collisions. An unanchored pattern is a latent footgun that removes real source from the
index without an obvious error.

## Proposed kit deltas

- When Research-SDD instructs a target repo to ignore its root-level investigation artifact
  directories, ALWAYS emit root-anchored patterns (`/corpus/`, `/retros/`, `/tools/`), never
  the unanchored form (`corpus/`, `tools/`). Document the collision rationale inline in the
  emitted `.gitignore` block so a future operator does not "simplify" the leading slash away.
- If the kit has a bootstrap/integration step that touches the target `.gitignore`, apply the
  anchored form there so it happens automatically instead of by operator memory.

## Follow-up

- Human review to accept the delta into the kit's corpus-integration guidance.
