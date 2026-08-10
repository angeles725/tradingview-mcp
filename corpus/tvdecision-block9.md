# Block 9 - The OHLCV collector: accumulating history past the 300-bar wall

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how the ~300-bar live-feed limit is overcome by a persistent, de-duplicated, atomically-saved CSV store
> that grows with each pull and can re-emit as the same bars JSON the analysis tools consume.
>
> Subject version: `analysis/collect.py` committed `bbd7beb` on branch `feat/quant-analysis-toolkit`
> (off `main` c05b8f5). Session 2026-08-05.
>
> Sources: `analysis/collect.py`, `analysis/test_collect.py` (local primary source). Preserved run:
> `sources/probes/decision-engine-session-2026-08-05.md`.
> Method: read-only citation of authored code plus a preserved live collect/stats cycle over
> OANDA:XAUUSD 15m. `[CERT]` marks a local `file:line`; `[CERT-live]` a preserved live measurement;
> `[CERT-hw]` a preserved test result; `[INFER]` an explicit deduction. METHODOLOGY/DESIGN block.
>
> Data-infrastructure layer. Directly answers the small-sample limitation flagged in [Block 7] and the
> weak-feedback limitation in [Block 8].

---

## 9.1 - Why: ~300 bars is too few for honest per-regime statistics `[CERT]`

The live feed returns roughly 300 bars per timeframe ([Block 1]); [Block 7]'s per-regime buckets held only
3-13 trades, far below the n>=30 the toolkit demands before calling anything an edge. The collector's
purpose is to break that wall by accumulating real history over repeated pulls (`analysis/collect.py:1`
header). `[INFER]` No better estimator fixes a small sample; only more data does.

## 9.2 - Merge semantics: dedup by time, forming-bar wins `[CERT]`

`merge` (`analysis/collect.py:63`) keys bars by timestamp: a genuinely new bar is appended, and a repeated
timestamp UPDATES the stored bar (`analysis/collect.py:71`) because the most recent live pull carries the
latest state of a bar that may still be forming. The result is returned sorted by time. A test pins both
the dedup/sort and the forming-bar update `[CERT-hw]` (`analysis/test_collect.py`,
`test_repeated_timestamp_updates_forming_bar`).

## 9.3 - Durability: atomic save, stdlib only `[CERT]`

`save_store` writes to a temp file and `os.replace`s it into place
(`analysis/collect.py:89`), so a crash mid-write never corrupts the store. The module uses only the
standard library (`analysis/collect.py:13`), so it runs unattended - e.g. from cron with the base Python,
no venv required. `[INFER]` These two choices are what make periodic, hands-off accumulation safe.

## 9.4 - Re-emit closes the loop `[CERT]` / `[CERT-live]`

`cmd_emit` (`analysis/collect.py:113`) prints the store as the exact bars JSON shape the analysis tools
read on stdin, so `collect.py --emit | analyze.py` (or backtest/decide) runs over the FULL accumulated
history instead of the last 300 bars. The live cycle confirmed the round trip: a 300-bar pull stored to
`analysis/data/OANDA_XAUUSD_15.csv`, `--stats` reported the 300 bars and their time span, and `--emit`
fed cleanly back into `analyze.py` `[CERT-live]`
(`sources/probes/decision-engine-session-2026-08-05.md`). `[INFER]` As pulls accumulate, the same command
silently gains history - the analysis code needs no change.

## 9.5 - What this unlocks and what it does not `[INFER]`

It unlocks n>=30 per-regime/per-condition statistics over time, which is the precondition for [Block 8]'s
Gate B to ever find a real edge and for the feedback loop to test gates A and C. It does NOT change any
guardrail: more data sharpens the estimates, it does not make a direction predictable. The store is
gitignored (accumulated market data is not source), so history lives locally and is not a committed
artifact.

## 9.6 - Connections

- **[Block 7]** - the small-sample limitation this collector exists to relieve.
- **[Block 8]** - the decision engine whose Gate B and feedback loop become informative once history is
  deep enough.
- **[Block 1]** - the ~300-bar live-feed limit that motivates persistence.
