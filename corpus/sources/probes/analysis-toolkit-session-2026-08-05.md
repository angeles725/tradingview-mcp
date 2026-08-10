# Probe — analysis/ quant toolkit live run (session 2026-08-05)

Subject: working tree of /home/cristian/TRADINGVIEW with NEW analysis/ toolkit (uncommitted).
Upstream base commit: 35ed7e9 on branch feat/harden-dangerous-capabilities.
Python venv: research-sdd-tools (numpy 2.5.1, scipy 1.18.0).
Live source: OANDA:XAUUSD 15m via `node src/cli/index.js ohlcv --count 300` over WSL2->Windows CDP (127.0.0.1:9222).

## quant tests [CERT-hw]
```
  ok  test_bootstrap_cone_fatter_than_gaussian_on_fat_tails
  ok  test_conditional_flags_thin_sample
  ok  test_ols_trend_recovers_known_slope
  ok  test_rsi_matches_wilder_reference
  ok  test_theilsen_robust_to_outlier
  ok  test_wilson_ci_bounds_and_symmetry

6/6 passed
```
## leakage guard [CERT-hw]
```
  ok  test_conditions_and_target_length_align
  ok  test_no_condition_perfectly_predicts_target

2/2 passed
```
## live assessment [CERT-live]
```
==========================================================================
 HONEST ASSESSMENT  XAUUSD  15m   n=300 bars (of 300 avail)
 Last price: 4247.275   |   cone horizon: 16 bars
==========================================================================

TREND (SIGNIFICANT)
  OLS slope   : +0.5896 price/bar   R^2=0.65   t=+23.3
  slope 95%CI : [+0.5398, +0.6395]
  Theil-Sen   : +0.4673 price/bar  (robust cross-check)

VOLATILITY (per-bar log-return sigma)
  close-to-close : 0.132%
  EWMA(0.94)     : 0.145%   (conditional / clustering-aware)
  Parkinson      : 0.126%   (OHLC range)
  Garman-Klass   : 0.126%   (most efficient)
  GARCH(1,1)     : 0.105%   (a=0.20 b=0.68, persist=0.89)
  -> implied daily move ~ +/-1.03%  (1 sigma)

MOMENTUM   RSI(14, Wilder) = 56.7   (corroboration only; high RSI != sell in a trend)

MONTE CARLO CONE  (16 bars ahead, zero-drift)
  model                         P5       P25       P50       P75       P95   P(up)
  gaussian                 4217.73   4235.32   4247.42   4259.41   4276.56    0.50
  bootstrap                4211.92   4232.20   4246.47   4261.29   4285.81    0.48
  student_t(df=2.1)        4196.76   4229.44   4246.99   4264.86   4298.96    0.50
  -> deliver the BAND (e.g. 90% inside P5..P95), never the median.
  -> if bootstrap/t P5..P95 is WIDER than gaussian, tails are fat: size down.

CONDITIONAL P(next bar up)   baseline = 0.572
  condition                   n    rate          95% CI    edge       p  verdict
  RSI<30 (oversold)           0    0.00     [0.00,1.00]   -0.57     nan  thin-sample
  RSI>70 (overbought)        38    0.55     [0.40,0.70]   -0.02   0.870  no-edge
  RSI 30-70 (neutral)       247    0.57     [0.50,0.63]   -0.01   0.898  no-edge
  bull candle (C>O)         170    0.57     [0.50,0.64]   -0.00   1.000  no-edge
  bear candle (C<O)         128    0.57     [0.48,0.65]   -0.00   1.000  no-edge
  3 up bars in a row         54    0.59     [0.46,0.71]   +0.02   0.785  no-edge
  -> 'thin-sample' (n<30) or a CI straddling baseline = NO edge.
==========================================================================
Guardrail: no line above predicts DIRECTION. This sizes the move and
attaches a probability. Risk management and an honest backtest decide P&L.
==========================================================================
```
