# Probe receipt — Per-instrument cone coverage flag (session 2026-08-12)

Artifact corpus/cone-coverage.json: per symbol|tf realized coverage of the nominal 90%/50%
cone bands + verdict, built by analysis/cone_coverage.py from the scored backfill.

```
OANDA:XAUUSD|D           c90=0.787 c50=0.447 n=47 too-tight
OANDA:XAUUSD|W           c90=0.847 c50=0.492 n=59 too-tight
OANDA:XAUUSD|M           c90=0.911 c50=0.481 n=79 reliable
OANDA:XAGUSD|D           c90=0.809 c50=0.489 n=47 too-tight
OANDA:XAGUSD|W           c90=0.881 c50=0.559 n=59 reliable
OANDA:XAGUSD|M           c90=0.924 c50=0.62 n=79 reliable
OANDA:SPX500USD|D        c90=0.957 c50=0.511 n=47 too-wide
OANDA:SPX500USD|W        c90=0.932 c50=0.458 n=59 reliable
OANDA:SPX500USD|M        c90=0.904 c50=0.466 n=73 reliable
OANDA:NAS100USD|D        c90=0.936 c50=0.426 n=47 reliable
OANDA:NAS100USD|W        c90=0.881 c50=0.508 n=59 reliable
OANDA:NAS100USD|M        c90=0.904 c50=0.37 n=73 reliable
OANDA:US2000USD|D        c90=0.936 c50=0.66 n=47 reliable
OANDA:US2000USD|W        c90=0.932 c50=0.576 n=59 reliable
OANDA:US2000USD|M        c90=0.904 c50=0.521 n=73 reliable
OANDA:DE30EUR|D          c90=0.915 c50=0.574 n=47 reliable
OANDA:DE30EUR|W          c90=0.881 c50=0.559 n=59 reliable
OANDA:DE30EUR|M          c90=0.932 c50=0.507 n=73 reliable
OANDA:WTICOUSD|D         c90=0.894 c50=0.511 n=47 reliable
OANDA:WTICOUSD|W         c90=0.932 c50=0.559 n=59 reliable
OANDA:WTICOUSD|M         c90=0.892 c50=0.5 n=74 reliable
OANDA:USDJPY|D           c90=0.872 c50=0.574 n=47 reliable
OANDA:USDJPY|W           c90=0.898 c50=0.475 n=59 reliable
OANDA:USDJPY|M           c90=0.909 c50=0.623 n=77 reliable
OANDA:EURUSD|D           c90=0.872 c50=0.489 n=47 reliable
OANDA:EURUSD|W           c90=0.898 c50=0.475 n=59 reliable
OANDA:EURUSD|M           c90=0.909 c50=0.636 n=77 reliable
OANDA:GBPUSD|D           c90=0.915 c50=0.447 n=47 reliable
OANDA:GBPUSD|W           c90=0.898 c50=0.458 n=59 reliable
OANDA:GBPUSD|M           c90=0.922 c50=0.506 n=77 reliable
OANDA:HK33HKD|D          c90=0.894 c50=0.489 n=47 reliable
OANDA:HK33HKD|W          c90=0.898 c50=0.508 n=59 reliable
OANDA:HK33HKD|M          c90=0.946 c50=0.595 n=74 reliable
OANDA:JP225USD|D         c90=0.894 c50=0.532 n=47 reliable
OANDA:JP225USD|W         c90=0.881 c50=0.475 n=59 reliable
OANDA:JP225USD|M         c90=0.877 c50=0.575 n=73 reliable
```
