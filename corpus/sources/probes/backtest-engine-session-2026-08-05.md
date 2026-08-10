# Probe — honest backtest engine (session 2026-08-05)

Subject: analysis/backtest.py (committed 91b7efc on branch feat/quant-analysis-toolkit, off main c05b8f5).
Live source: OANDA:XAUUSD 15m, 300 bars via tv CLI. Python venv research-sdd-tools.

## tests [CERT-hw]
```
  ok  test_cost_monotonically_reduces_expectancy
  ok  test_ema_tracks_and_warms_up
  ok  test_fills_are_next_open_no_lookahead
  ok  test_no_free_edge_on_random_walk
  ok  test_signal_on_last_bars_is_dropped_not_peeked
  ok  test_thin_sample_flagged

6/6 passed
```
## ema_trend OVERLAPPING (naive, autocorrelated) [CERT-live]
```
 191 signals -> 182 overlapping trades over 300 bars
FULL SAMPLE   [EDGE]
  trades      : 182    win rate: 53.3%
  expectancy  : +13.47 bps/trade (NET)   gross +15.47 - cost 2.00
  mean 95% CI : [+7.31, +19.88] bps   t=+4.18
  trades      : 92    win rate: 41.3%
  expectancy  : -2.36 bps/trade (NET)   gross -0.36 - cost 2.00
  mean 95% CI : [-7.33, +2.70] bps   t=-0.91
  trades      : 90    win rate: 65.6%
  expectancy  : +29.65 bps/trade (NET)   gross +31.65 - cost 2.00
  mean 95% CI : [+19.51, +40.71] bps   t=+5.44
VERDICT
  Net edge survives costs AND out-of-sample. Worth Replay practice — still
```
## ema_trend NON-OVERLAPPING (honest, independent) [CERT-live]
```
==========================================================================
 HONEST BACKTEST  XAUUSD 15m   rule=ema_trend  hold=8  cost=1.0bps/side
 191 signals -> 26 non-overlapping trades over 300 bars
==========================================================================

FULL SAMPLE   [THIN-SAMPLE]
  trades      : 26    win rate: 50.0%
  expectancy  : +9.14 bps/trade (NET)   gross +11.14 - cost 2.00
  mean 95% CI : [-5.38, +24.65] bps   t=+1.17
  profit factor: 1.91

IN-SAMPLE (first 60%)   [THIN-SAMPLE]
  trades      : 15    win rate: 33.3%
  expectancy  : -5.76 bps/trade (NET)   gross -3.76 - cost 2.00
  mean 95% CI : [-20.54, +7.76] bps   t=-0.77
  profit factor: 0.57

OUT-OF-SAMPLE (last 40%)   [THIN-SAMPLE]
  trades      : 11    win rate: 63.6%
  expectancy  : +26.77 bps/trade (NET)   gross +28.77 - cost 2.00
  mean 95% CI : [+2.27, +53.47] bps   t=+1.95
  profit factor: 5.73

VERDICT
  Too few trades to conclude anything. Need ~30+; collect more or widen the rule.
==========================================================================
Reminder: this measures a RULE, not the future. Costs + sample + overfit are
the three liars; risk management decides survival regardless of the edge.
==========================================================================
```
