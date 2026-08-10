# Probe — decision engine + collector (session 2026-08-05)

Subject: analysis/{decide.py,collect.py} committed 8e3247f/bbd7beb on feat/quant-analysis-toolkit.
Live: OANDA:XAUUSD 15m 300 bars via tv CLI.

## tests [CERT-hw]
```
-- test_decide --
5/5 passed
-- test_collect --
4/4 passed
```
## live decision [CERT-live]
```
  >>> NO-TRADE  [none]   no defensible direction (Gate A)
  [FAIL] A_direction    trend sig (R^2=0.65), regime=chop (want trend-up), VR4=1.05
  Flat is a position. No setup meets the bar; the honest move is to wait.
```
## process feedback [CERT-live]
```
    NO-TRADE    238  (100.0%)
    BUY           0  (0.0%)
    SELL          0  (0.0%)
  edge precondition: in-sample edge=thin-sample (exp -0.6bps)
  simulated trades : 0
  The process stayed FLAT the whole window — no setup cleared all gates.
```
## collector cycle [CERT-live]
```
store: /home/cristian/TRADINGVIEW/analysis/data
  OANDA_XAUUSD_15.csv             300 bars   time 1785510000..1785962700
```
