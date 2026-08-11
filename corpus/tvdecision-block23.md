# Block 23 - Record-side contamination guard, and the threshold that was too loose

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> cross-symbol contamination had TWO sides; [Block 21] closed only the scoring side. This closes the record
> side — and then catches that the first guard threshold was too loose to catch a live case, tightening it.
> A short block about doing the fix, then verifying the fix actually fires.
>
> Subject version: `analysis/forecast.py` + `analysis/periodic.py` on branch `feat/quant-analysis-toolkit`.
> Session 2026-08-11.
>
> Sources: `analysis/forecast.py`, `analysis/periodic.py`, `analysis/test_forecast.py` (local primary
> source). Preserved run: `sources/probes/record-guard-session-2026-08-11.md`.
> Method: read-only citation of authored code + a preserved live measurement + TDD. `[CERT]` marks a local
> `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block. Rigor layer.

---

## 23.1 - The second side of the bug `[CERT-live]`

[Block 21]/C1 guarded the SCORING side (a record scored against another symbol's bars). The RECORD side was
still open: a feed-not-ready symbol switch recorded 8 periodic-daily forecasts (2026-08-09) whose S0 was
another symbol's price — EURUSD S0=7757 (SPX's), SPX S0=1.15 (EURUSD's), USDJPY S0=4390 (gold's)
(`sources/probes/record-guard-session-2026-08-11.md`) `[CERT-live]`. `[INFER]` These can never mature — the
scoring guard rejects their absurd realized jump — so they sit as dead pending records, and any that DID
mature would poison the calibration count.

## 23.2 - The guard `[CERT]`

`s0_contaminated(symbol, tf, s0, store_dir, max_dev)` compares S0 to the symbol's own OHLCV-store median
close and returns True when the deviation exceeds `max_dev` (`analysis/forecast.py`) `[CERT]`. It is wired
into BOTH record paths — the 15m `forecast.py record --store` and the periodic `periodic.py --ohlcv-store`
(`analysis/periodic.py`) `[CERT]` — with the collect/periodic hooks passing `$DATA`. A contaminated pull is
skipped, not logged; a thin (<20 bars) or missing store returns False, so it never false-rejects.

## 23.3 - The first threshold was too loose `[CERT-live]`

The first cut shipped `max_dev=0.5`. A later live batch recorded SPX500 S0=4372.76 and USDJPY S0=4372.99 —
both GOLD's price. SPX vs its store median 7756.30 is 44% off, BELOW 0.5, so the guard PASSED it: at
threshold 0.50 only 1 of the 2 was detectable; at 0.15 both were
(`sources/probes/record-guard-session-2026-08-11.md`) `[CERT-live]`. `[INFER]` A 0.5 threshold only catches
contamination between price scales that differ by more than 2x; same-order pairs (gold ~4372 vs SPX ~7756,
or EURUSD ~1.15 vs GBPUSD ~1.35) slip through.

## 23.4 - Tightened to 0.15 `[CERT]`

Default `max_dev` lowered to 0.15 (`analysis/forecast.py`) `[CERT]`. `[INFER]` It catches even same-scale
neighbours (EURUSD 1.15 vs GBPUSD 1.35 = +17%) while staying well above any real move for these instruments
over the store window (forex ~1-3%, indices/gold <10%). Test extended: a +17% neighbour price is now flagged,
a 2% drift still passes. The 2 live contaminated records were purged (both gold's price, both unresolved) —
log 199 records, 0 contaminated.

## 23.5 - The standing lesson `[INFER]`

`[INFER]` Two lessons compound here. First, a bug fix is not done at the first plausible guard — the SAME
class of bug had a second side (record vs score) and the first guard had a hole (threshold), each found only
by continuing to look at live data, not by trusting the green test. Second, this is the THIRD contamination
finding of the arc ([Block 21] scoring, C3 record, this threshold): the feed-not-ready symbol-switch race is
the root cause, and these guards are defense-in-depth over a data-source that lies during a switch. A deeper
fix would verify the chart actually settled on the requested symbol before the pull — noted, not yet built.

## 23.6 - Connections

- **[Block 21]** - the scoring-side guard (C1) this is the record-side twin of.
- **IMPROVEMENT-BACKLOG #C3** - the record guard; this block adds the threshold tightening.
- **[Block 22]** - the same "verify the fix actually fires on the hold-out / live data" discipline.
