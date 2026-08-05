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
| `quant.py` | Pure numerical primitives (trend, volatility, RSI, EMA, Monte Carlo, conditional probability, bootstrap CI). No I/O. |
| `analyze.py` | Reads TradingView OHLCV JSON on stdin, prints an honest assessment report. |
| `backtest.py` | Turns a candidate RULE into a validated edge — or refutes it — with costs, out-of-sample split, and independent (non-overlapping) trades. |
| `test_quant.py` | Sanity tests for the math (RSI, Wilson CI, OLS, Theil-Sen, cones). |
| `test_analyze.py` | Lookahead-leakage guard for the conditional builder. |
| `test_backtest.py` | Next-open fill / no-lookahead, cost monotonicity, thin-sample, no-free-edge-on-random-walk. |

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

# Backtest a rule (ema_trend | rsi_oversold | three_up)
node src/cli/index.js ohlcv --count 300 \
  | $VENV analysis/backtest.py --rule ema_trend --hold 8 --cost-bps 1.0
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
- **Regime** — a variance ratio (Lo–MacKinlay: VR>1 trending/momentum, VR<1
  mean-reverting, ~1 random) and a rolling-R² label (`trend-up` / `trend-down` /
  `chop`). A trend rule that looks good only inside a trend is not an edge;
  regime tells you when to trust a result.
- **Serial dependence** — a **stationary (block) bootstrap** (Politis–Romano)
  resamples contiguous blocks, preserving the short-range dependence the i.i.d.
  bootstrap destroys. It is the honest CI for autocorrelated data; the backtest
  reports it alongside the i.i.d. CI, and it splits trade expectancy **by
  regime** so a trend-only edge is exposed.
- **Conditional P(next bar up)** — for each RSI/candle condition, the rate
  against the unconditional baseline, with a **Wilson score 95% CI** and a
  **binomial test** p-value. A bucket is only an *edge* when n ≥ 30 AND the CI
  clears the baseline. `thin-sample` and CI-straddles-baseline both mean **no
  edge** — the guardrail that stops a 12-sample bucket posing as a signal.

## The backtest engine — how it resists the three liars

`backtest.py` measures a rule the honest way (see Block 3):

- **Costs** — transaction cost is subtracted per side; the report shows gross vs
  net so you see exactly how much cost eats. Most "edges" die here.
- **Sample** — `n < 30` is flagged `thin-sample`; the mean edge carries a
  **bootstrap 95% CI**, and an edge whose CI includes 0 is not real.
- **Overfit** — an in-sample / out-of-sample split; an edge that survives only
  in-sample is overfit and refused.
- **No lookahead** — a signal on bar `t` fills at the **open of `t+1`** and exits
  at the open of `t+1+hold`. The rule never sees the bar it trades into.
- **Independent trades (default)** — non-overlapping fills, so the CI and t-stat
  are not inflated by autocorrelation. `--overlap` gives the raw
  signal-conditional view (every signal), which overstates significance and must
  never be read as a CI. On live gold, `ema_trend` looked like a `+13 bps` edge
  overlapping (182 trades) but collapsed to a non-significant `thin-sample`
  (26 independent trades, CI crossing 0) once autocorrelation was removed — the
  overlapping view had manufactured the edge.

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
