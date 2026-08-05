# Analysis toolkit — honest, range-based chart assessment

Persistent, reproducible numerical methods for assessing a live TradingView
chart. This replaces the ephemeral `gold_*.py` scratch scripts from earlier
sessions (which were lost); the point of this directory is that the methods
survive and stay testable.

## What it does — and refuses to do

It **sizes** the move and attaches a **probability**. It does **not** predict
direction. Every probabilistic output is a range with a probability, never a
single point price.

## Files

| File | Purpose |
|------|---------|
| `quant.py` | Pure numerical primitives (trend, volatility, RSI, Monte Carlo, conditional probability). No I/O. |
| `analyze.py` | Reads TradingView OHLCV JSON on stdin, prints an honest report. |
| `test_quant.py` | Sanity tests for the math (RSI, Wilson CI, OLS, Theil-Sen, cones). |
| `test_analyze.py` | Lookahead-leakage guard for the conditional builder. |

## Run

```bash
# From the repo root. Use the scipy-enabled venv.
VENV=~/.local/share/research-sdd-tools/venv/bin/python3

# Tests
$VENV analysis/test_quant.py
$VENV analysis/test_analyze.py

# Live assessment (XAUUSD 15m, 16-bar forward cone = 4h)
node src/cli/index.js ohlcv --count 300 \
  | $VENV analysis/analyze.py --symbol XAUUSD --tf 15 --horizon 16

# Machine-readable
node src/cli/index.js ohlcv --count 300 \
  | $VENV analysis/analyze.py --tf 15 --json
```

## Methods and why each was chosen

- **Trend** — OLS slope with R², a slope t-stat and 95% CI, plus a robust
  **Theil–Sen** cross-check. A slope without significance is eyeballing; a
  slope sensitive to one spike is a lie. Both are reported.
- **Volatility** — five estimators side by side: close-to-close (baseline),
  **EWMA(0.94)** and **GARCH(1,1)** for volatility *clustering* (the "vol of
  now"), and **Parkinson** / **Garman–Klass** which use the OHLC range and are
  far more efficient than close-only. The cone uses GARCH if it fits, else EWMA.
- **Monte Carlo cone** — three tail models: Gaussian (assumption-free
  baseline), **bootstrap** of the actual returns (real fat tails and skew), and
  **Student-t** (parametric fat tails). When the bootstrap/t band is wider than
  Gaussian, tails are fat and position size must come down. Run zero-drift so
  P(up) ≈ 0.50 by construction — no directional bet is injected.
- **Conditional P(next bar up)** — for each RSI/candle condition, the rate
  against the unconditional baseline, with a **Wilson score 95% CI** and a
  **binomial test** p-value. A bucket is only an *edge* when n ≥ 30 AND the CI
  clears the baseline. `thin-sample` and CI-straddles-baseline both mean **no
  edge** — the guardrail that stops a 12-sample bucket posing as a signal.

## The lookahead trap (why `test_analyze.py` exists)

A condition on decision bar `t` may use only information known at the close of
`t`. If it references `t+1` it leaks the target and prints a fake ~100% edge —
and the statistical machinery (Wilson, binomial) will happily bless it. Only
correct temporal alignment prevents this. The leakage guard fails the build if
any thick bucket hits an implausibly perfect rate.

## Non-negotiable guardrails

1. Deliver a **range with a probability**, never a single point price.
2. **No method here predicts direction** — trend/RSI/GARCH refine size and
   confidence, not the arrow.
3. Validate any rule with an **honest backtest** (transaction costs + ≥ ~30
   trades) before real money.
4. **Risk management first** — position sizing and stop-loss decide survival.
5. The live feed returns **~300 bars/timeframe**; treat that as the real
   history horizon.
