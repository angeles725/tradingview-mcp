# Test runner PINNED to the scipy-enabled interpreter.
#
# Why this exists: the base `python3` has NO scipy, so `python3 -m pytest` silently
# runs the most fragile numerics (GARCH optimize, mc_student_t, HAC/t.ppf) in their
# `_HAS_SCIPY=False` fallback and scipy-guarded tests early-return — a FALSE GREEN.
# `make test` refuses to run on any interpreter lacking scipy/pytest, so that gap
# cannot reopen by accident. See retros/2026-08-07-scipy-venv-testing-gap.md.
#
# Override the interpreter if yours lives elsewhere:  make test VENV_PY=/path/to/python

VENV_PY ?= $(HOME)/.local/share/research-sdd-tools/venv/bin/python3

.PHONY: test test-guard

## test: run the full analysis suite on the scipy venv (fails closed if scipy is absent)
test: test-guard
	$(VENV_PY) -m pytest analysis/ -q

## test-guard: refuse to proceed unless the chosen interpreter has scipy AND pytest
test-guard:
	@test -x "$(VENV_PY)" || { \
	  echo "ERROR: scipy interpreter not found at $(VENV_PY)"; \
	  echo "  Create the research-sdd venv or pass VENV_PY=/path/to/python."; \
	  exit 1; }
	@$(VENV_PY) -c "import scipy, pytest" 2>/dev/null || { \
	  echo "ERROR: $(VENV_PY) lacks scipy and/or pytest — refusing to run."; \
	  echo "  Running pytest here would give FALSE GREENS on the scipy code paths."; \
	  exit 1; }
