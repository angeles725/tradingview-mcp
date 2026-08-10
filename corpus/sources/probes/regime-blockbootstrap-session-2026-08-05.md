# Probe — regime detection + block bootstrap (session 2026-08-05)

Subject: analysis/{quant.py,analyze.py,backtest.py} committed 20afcae on feat/quant-analysis-toolkit.
Live: OANDA:XAUUSD 15m 300 bars via tv CLI.

## tests [CERT-hw]
```
-- test_quant --
10/10 passed
-- test_backtest --
7/7 passed
```
## regime section [CERT-live]
```
REGIME   now = chop
  window mix   : chop:114  trend-down:60  trend-up:126
  variance ratio: VR2=1.02  VR4=1.05  VR8=1.08   (>1 trending/momentum, <1 mean-reverting, ~1 random)

```
## backtest ema_trend block-CI + regime split [CERT-live]
```
FULL SAMPLE   [THIN-SAMPLE]
  trades      : 26    win rate: 50.0%
  mean 95% CI : [-5.38, +24.65] bps   t=+1.17
  block-boot CI: [-6.37, +24.96] bps  (serial-dependence honest; wider = trades cluster by regime)
BY REGIME (entry-bar regime; is the edge only inside a trend?)
  trend-up     n= 13   expectancy +11.16 bps
  trend-down   n=  3   expectancy -10.63 bps
  chop         n= 10   expectancy +12.44 bps
  trades      : 15    win rate: 33.3%
  mean 95% CI : [-20.54, +7.76] bps   t=-0.77
  trades      : 11    win rate: 63.6%
  mean 95% CI : [+2.27, +53.47] bps   t=+1.95
VERDICT
  Too few trades to conclude anything. Need ~30+; collect more or widen the rule.
```
