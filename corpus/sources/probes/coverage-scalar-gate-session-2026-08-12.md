# Probe receipt — Coverage-scalar cone widener: walk-forward honesty gate (session 2026-08-12)

Walk-forward per symbol|tf over the real cone backfill (corpus/forecasts-backfill-cone.jsonl,
1804 scored, 30 groups, n 47-77/group). Fit k on train 70% (by made_at), measure raw vs k-scaled
coverage on the held-out 30%. VERDICT: NO-SHIP (improved 0 / harmed 2; motivating metals absent from pool).
```
group                     n      k   raw90   adj90   raw50   adj50  flag
OANDA:DE30EUR|D          15   1.02    0.93    0.93    0.47    0.53  
OANDA:DE30EUR|M          22   1.01    1.00    1.00    0.45    0.45  
OANDA:DE30EUR|W          18   1.14    0.89    0.89    0.72    0.72  
OANDA:EURUSD|D           15   1.31    0.93    1.00    0.67    0.87  
OANDA:EURUSD|M           24   1.33    0.96    0.96    0.71    0.75  
OANDA:EURUSD|W           18   1.10    1.00    1.00    0.67    0.67  
OANDA:GBPUSD|D           15   1.27    0.93    1.00    0.60    0.60  
OANDA:GBPUSD|M           24   1.04    0.96    0.96    0.58    0.67  
OANDA:GBPUSD|W           18   1.08    1.00    1.00    0.44    0.44  
OANDA:HK33HKD|D          15   1.15    0.87    0.87    0.47    0.53  
OANDA:HK33HKD|M          23   0.72    0.91    0.74    0.52    0.43  HARMED (tightened a fine group)
OANDA:HK33HKD|W          18   1.18    1.00    1.00    0.67    0.83  
OANDA:JP225USD|D         15   1.27    1.00    1.00    0.60    0.67  
OANDA:JP225USD|M         22   1.10    0.91    0.91    0.64    0.64  
OANDA:JP225USD|W         18   0.94    0.78    0.78    0.28    0.28  
OANDA:NAS100USD|D        15   1.03    1.00    1.00    0.40    0.40  
OANDA:NAS100USD|M        22   0.89    0.86    0.82    0.36    0.36  
OANDA:NAS100USD|W        18   0.96    0.78    0.78    0.56    0.50  
OANDA:SPX500USD|D        15   0.99    1.00    1.00    0.47    0.47  
OANDA:SPX500USD|M        22   1.08    0.91    0.95    0.45    0.55  
OANDA:SPX500USD|W        18   0.94    0.89    0.89    0.50    0.44  
OANDA:US2000USD|D        15   1.04    1.00    1.00    0.87    0.93  
OANDA:US2000USD|M        22   1.34    0.91    1.00    0.59    0.77  
OANDA:US2000USD|W        18   0.96    0.89    0.89    0.61    0.61  
OANDA:USDJPY|D           15   1.47    0.87    0.93    0.60    0.80  
OANDA:USDJPY|M           24   1.12    0.96    0.96    0.62    0.62  
OANDA:USDJPY|W           18   1.31    1.00    1.00    0.67    0.94  
OANDA:WTICOUSD|D         15   1.29    0.93    0.93    0.27    0.53  
OANDA:WTICOUSD|M         23   1.07    0.91    0.91    0.48    0.57  
OANDA:WTICOUSD|W         18   0.78    0.89    0.83    0.50    0.44  HARMED (tightened a fine group)

SUMMARY: improved=0  harmed=2
HARMED groups (scalar tightened an already-ok cone OOS): ['OANDA:HK33HKD|M', 'OANDA:WTICOUSD|W']
```

Pool composition check (independent re-measure):
```
total scored: 1804 | groups: 30
XAU/XAG present?: ABSENT
```
