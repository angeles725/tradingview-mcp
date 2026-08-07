# Retro — tests silently skip scipy paths under base python3 (2026-08-07)

## What happened
While implementing fix #12 (Student-t `df>2` guard in `analysis/quant.py`), the new red test
`test_mc_student_t_guards_degenerate_df` **passed before the fix existed** — a false green. Cause: the
base `python3` used for `python3 -m pytest` has **no scipy**, so `quant._HAS_SCIPY` is False and the test
hit its `if not q._HAS_SCIPY: return` early-exit. Running the same file with the scipy-enabled venv
produced the true red (`model=student_t(df=1.5)`, no guard), the fix was applied, then true green.

## Why it matters
`python3 -m pytest` reports green while **never executing** the scipy-dependent code:
`garch11_vol` (scipy.optimize), `mc_student_t` (scipy.stats.t), and HAC/`t.ppf` significance. Every one
of those runs its `_HAS_SCIPY=False` fallback under the base interpreter, and scipy-guarded tests
early-return. The most numerically fragile parts of the toolkit are exactly the ones the default test
command does not test.

## Correct procedure
- Scipy venv (has scipy 1.18 / numpy 2.5, lacks pytest): `~/.local/share/research-sdd-tools/venv/bin/python3`
- Run the real suite via each file's standalone `__main__` runner:
  ```
  VENV=~/.local/share/research-sdd-tools/venv/bin/python3
  for f in analysis/test_*.py; do "$VENV" "$f"; done
  ```
- Any change touching a scipy path (#10, #12, #1) must be validated with the venv, not base python3.

## Follow-up (added to backlog)
- Install pytest into the scipy venv, or add a `make test` / script that pins the scipy interpreter, so
  the default test path can no longer silently skip the fragile numerics.

## Applied
Re-ran fix #12 red→green on the scipy venv (32 tests pass across all files); recorded the venv procedure
in `corpus/IMPROVEMENT-BACKLOG.md`.
