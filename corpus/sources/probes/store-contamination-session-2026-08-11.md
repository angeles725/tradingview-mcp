# Preserved session — store contamination discovered, root-caused, and cleaned (2026-08-11)

Live receipt for tvdecision Block 24. Branch `feat/quant-analysis-toolkit`.
Root-cause fix commit `fd6c158`. Stores (`analysis/data/*.csv`) are git-untracked.

## 1. Discovery — the stores, not just the log

The record-side S0 guard (B23) false-rejected a CORRECT SPX500 S0=7747 and JP225
S0=67219 during a live batch. Cause: the guard's reference is the symbol's own
OHLCV-store median — and the stores themselves were massively contaminated by the
same feed-not-ready symbol-switch race, accumulated over a long time:

```
symbol      store median   should be     verdict
SPX500USD        3768.85      ~7758.00    97% cross-symbol (1001/1032 outliers)
USDJPY           4125.27       ~159.00    dominated by gold's ~4372
JP225USD        52903.10     ~67000.00    heavily mixed
DE30EUR         24487.20     ~26340.00    mixed (min 2462, max 26440)
EURUSD (median)     1.16         ~1.15    median OK but max 7754 (SPX bars inside)
```

## 2. Root cause and the fix

`getOhlcv` (`src/core/data.js`) read the bars series directly and never verified
the symbol; after a symbol switch, a not-yet-settled feed left the PREVIOUS
symbol's bars in place. Fix: `getOhlcv` now also reads `CHART_API.symbol()` and,
when the caller passes `--expect-symbol`, returns
`{success:false, reason:'symbol-mismatch', expected, actual}` instead of the wrong
bars. Wired into both hook pulls. Live verification:

```
chart on XAUUSD, --expect-symbol OANDA:XAUUSD   -> bars returned
chart on XAUUSD, --expect-symbol OANDA:SPX500USD -> {success:false, symbol-mismatch, actual: OANDA:XAUUSD}
no --expect-symbol                               -> normal (backward compatible)
```

This is the SOURCE-level guard, third in a defense chain with the record-side
`s0_contaminated` (B23) and the scoring-side `MAX_REALIZED_JUMP` (B21).

## 3. Cleanup with an external clean reference

The store's own median was too contaminated to self-clean (SPX median = 3768).
Used the ALREADY-PURGED forecast log's per-symbol S0 median as an external clean
reference (SPX 7756.4, USDJPY 159.22, JP225 66819 — all correct), then kept only
store bars within `[ref/1.5, ref*1.5]` (cross-symbol prices are always multiples
off; real drift stays under 50%):

```
symbol      before  kept  dropped   new median   ref      dev
SPX500USD     1032   353     679      7758.20    7756.40   0%
JP225USD       985   584     401     65741.60   66819.00   2%
XAUUSD         947   822     125      4180.77    4363.95   4%
USDJPY        1021   279     742       123.11     159.22  23%  -> REBUILT
```

Nine stores cleaned to dev 0-4%. USDJPY's cleaned median stayed 23% off (a ~123
cluster inside the band), so its store was REBUILT (deleted; the guarded hook
refills it). After cleanup the guard passes SPX 7747 / JP225 67000 / USDJPY 159.

## 4. Implication

Backfill and conformal are derived from these stores, so those artifacts may be
skewed and were regenerated from the cleaned stores. The scorecard cov90 comes
from the forecast LOG (S0 + realized), which the record/scoring guards already
protect, so it is far less affected.
