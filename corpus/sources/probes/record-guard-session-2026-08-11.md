# Preserved session — record-side contamination guard + threshold tightening (2026-08-11)

Live receipt for tvdecision Block 23. Branch `feat/quant-analysis-toolkit`.
`make test` → 128 passed (scipy venv).

## 1. The second side of the contamination bug

[Block 21]/C1 fixed cross-symbol contamination on the SCORING side
(MAX_REALIZED_JUMP). The RECORD side was still open: a feed-not-ready symbol
switch recorded 8 periodic-daily forecasts (2026-08-09) with a wrong-symbol S0 —
EURUSD S0=7757 (SPX's price), SPX S0=1.15 (EURUSD's), USDJPY S0=4390 (gold's).
They can never mature (the scoring guard rejects the absurd realized jump).

## 2. The guard

`s0_contaminated(symbol, tf, s0, store_dir, max_dev)` compares S0 to the symbol's
own OHLCV-store median close; True if the deviation exceeds `max_dev`. Wired into
both record paths — `forecast.py record --store` and `periodic.py --ohlcv-store`
— with the collect/periodic hooks passing `$DATA`. A contaminated pull is skipped,
not logged. False when the store is thin (<20 bars) or missing → never a false
reject.

## 3. The threshold was too loose (0.5 -> 0.15)

The first cut shipped `max_dev=0.5`. It let a live case slip: a batch recorded
SPX500 S0=4372.76 and USDJPY S0=4372.99 — both GOLD's price (~4372). SPX vs its
store median 7756.30 is only 44% off — BELOW the 0.5 threshold — so the guard
passed it.

```
detectable contaminated records:
  threshold 0.50 -> 1   (SPX 44%-off slips through)
  threshold 0.15 -> 2   (both caught)
```

Tightened default to `max_dev=0.15`. It catches even same-scale-neighbour swaps
(EURUSD 1.15 vs GBPUSD 1.35 = +17%) while staying well above any real 1h/1-day
move for these instruments (forex ~1-3%, indices/gold <10% over the store window).
Test `test_s0_contaminated_flags_cross_symbol_price` extended: a +17% neighbour
price is now flagged; a 2% drift still passes.

## 4. Purge

Removed the 2 live contaminated records (SPX 4372.76 vs median 7756.30, USDJPY
4372.99 vs median 159.24) — both gold's price, both unresolved, no calibration
lost. Log: 199 records, 0 contaminated.
