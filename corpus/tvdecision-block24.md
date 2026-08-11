# Block 24 - The contamination was in the stores: a source-level guard and a mass cleanup

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> the contamination arc's final turn. Guarding the RECORD side ([Block 23]) exposed that the OHLCV STORES
> — the reference the guard trusts, and the source of backfill/conformal — were themselves massively
> contaminated by the same race. Fixes it at the SOURCE (`getOhlcv`), cleans the stores from an external
> clean reference, and closes the loop with a three-layer defense.
>
> Subject version: `src/core/data.js` + `analysis/*` on branch `feat/quant-analysis-toolkit`. Session
> 2026-08-11.
>
> Sources: `src/core/data.js`, `src/cli/commands/data.js`, `analysis/collect-hook.sh`,
> `analysis/periodic-hook.sh` (local primary source). Preserved run:
> `sources/probes/store-contamination-session-2026-08-11.md`.
> Method: read-only citation of authored code + a preserved live measurement + cleanup receipt. `[CERT]`
> marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block. Rigor layer.

---

## 24.1 - A false positive that told the truth `[CERT-live]`

The [Block 23] record guard false-rejected a CORRECT SPX500 S0=7747 and JP225 S0=67219 on a live batch. The
guard's reference is the symbol's own OHLCV-store median — so a false positive on a correct price means the
STORE median is wrong. It was: SPX500's store median was 3768.85 (should be ~7758), USDJPY's 4125.27 (should
be ~159), JP225's 52903 (should be ~67000); SPX was 97% cross-symbol bars
(`sources/probes/store-contamination-session-2026-08-11.md`) `[CERT-live]`. `[INFER]` The feed-not-ready race
had been contaminating the persistent stores — not just the forecast log — over a long time, silently,
because nothing downstream re-checked the symbol.

## 24.2 - The root cause, finally named `[CERT]`

`getOhlcv` (`src/core/data.js`) read the bars series (`BARS_PATH`) directly and never verified which symbol
those bars belonged to `[CERT]`. After `setSymbol`, the DOM legend and the internal bars series settle on
DIFFERENT clocks (the [Block 23]/wait.js readiness check watches the legend, not the series), so a pull could
return the PREVIOUS symbol's bars. Every prior guard (scoring B21, record B23) was a backstop AFTER the bad
data was already produced; this is the first that addresses the production itself.

## 24.3 - The source-level fix `[CERT]`

`getOhlcv` now also reads `CHART_API.symbol()` and, when the caller passes `expectSymbol`, returns
`{success:false, reason:'symbol-mismatch', expected, actual}` instead of the wrong bars
(`src/core/data.js`) `[CERT]`; exposed as `ohlcv --expect-symbol` (`src/cli/commands/data.js`) and wired into
both hook pulls (`analysis/collect-hook.sh`, `analysis/periodic-hook.sh`) `[CERT]`. Live-verified: correct
symbol returns bars, a mismatch is refused, and no flag preserves old behavior
(`sources/probes/store-contamination-session-2026-08-11.md`) `[CERT-live]`. `[INFER]` With this, collect never
MERGES and record never LOGS contaminated bars — the store stays clean at the source.

## 24.4 - Cleaning a store whose own median lies `[CERT-live]`

The stores could not self-clean (SPX median 3768 is contamination, not signal). The fix used an EXTERNAL clean
reference: the already-purged forecast log's per-symbol S0 median (SPX 7756, USDJPY 159, JP225 66819 — all
correct), keeping only bars within `[ref/1.5, ref*1.5]` — cross-symbol prices are always multiples off, real
drift stays under 50%. SPX 1032->353, JP225 985->584, nine stores cleaned to 0-4% median deviation
(`sources/probes/store-contamination-session-2026-08-11.md`) `[CERT-live]`. USDJPY's cleaned median stayed 23%
off (a ~123 cluster inside the band) so its store was REBUILT (deleted; the guarded hook refills it). Backfill
and conformal, derived from the stores, were regenerated from the cleaned data.

## 24.5 - The arc's lesson `[INFER]`

`[INFER]` Four turns, one root cause: the feed-not-ready symbol-switch race. Scoring guard (B21) -> record
guard (B23) -> tighter threshold (B23) -> and only here the SOURCE. Each layer was found by watching live data
after the previous "fix", never by a green test. Two standing lessons: (1) a guard is only as good as its
reference — the record guard's store reference was itself poisoned, so the fix had to go upstream; (2) defense
in depth beats a single check for a lying data source — the three layers (source / record / scoring) now each
catch what the others might miss. The deeper prevention (a settle-verified pull) is now BUILT here, not just
noted.

## 24.6 - Connections

- **[Block 23]** - the record guard whose false positive exposed the store contamination.
- **[Block 21]** - the scoring guard; the third layer of the same defense.
- **IMPROVEMENT-BACKLOG #C5** - the source-level `--expect-symbol` guard and the store cleanup.
