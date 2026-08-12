# Block 28 - Per-instrument cone coverage flag: warn when a band lies

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> the pooled cone coverage (~0.90 of the 90% band) is an AVERAGE that hides per-instrument reality —
> some symbol|tf cones run systematically too tight, so a stop sized off their P5/P95 breaches far more
> than the nominal 10%. This documents the HONEST diagnostic: measure realized coverage per symbol|tf from
> the scored backfill, stamp a verdict (reliable / too-tight / too-wide), and surface a one-line warning on
> the live cone. Crucially it is a FLAG, not an overfit correction — the widenings that tried to auto-fix
> these cones ([Block 20], [Block 22], and the scalar rejected this session [Block 30]) all failed OOS.
>
> Subject version: `analysis/cone_coverage.py` + `analysis/analyze.py` on branch
> `feat/quant-analysis-toolkit`. Session 2026-08-12. Commit `3bbf57a`.
>
> Sources: `analysis/cone_coverage.py`, `analysis/analyze.py` (local primary source). Preserved run:
> `sources/probes/cone-coverage-flag-session-2026-08-12.md`, and the emitted artifact
> `corpus/cone-coverage.json`.
> Method: read-only citation of authored code + a preserved live measurement. `[CERT]` marks a local
> `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block. Rigor layer.

---

## 28.1 - The average lies about the instrument `[CERT]`

The backfill showed the cones covering ~88-90% of the nominal 90% band IN AGGREGATE, and that pooled number
is the toolkit's strongest result. But the module's own header states the danger the aggregate buries:
gold's DAILY 90% band only covered 79%, so "a stop sized off it is breached ~21% of the time, not 10%"
(`analysis/cone_coverage.py:6-11`) `[CERT]`. `[INFER]` A pooled metric averages a too-tight metals cone
against a too-wide index cone and returns a reassuring ~0.90 that is true of NO single instrument you would
actually trade — the per symbol|tf breakdown is the only honest unit for stop sizing.

## 28.2 - Verdict by threshold, not by fit `[CERT]`

`_verdict(cover_90, n)` maps realized coverage of the 90% band to one of four labels with fixed thresholds:
`reliable` when |cover_90 - 0.90| is within 0.05, `too-tight` when cover_90 < 0.85 (DANGER: stops breach
more than nominal), `too-wide` when cover_90 > 0.95 (over-conservative), `insufficient` when n < `MIN_N`
(= 30) (`analysis/cone_coverage.py:46-53`, `analysis/cone_coverage.py:31`) `[CERT]`. `[INFER]` The verdict is
a bucketed READING of history, not a parameter fit to it — nothing here is tuned to minimize an error, so
there is no free parameter to overfit; the flag can only ever say "this band ran tight/wide/true," never
reshape the band.

## 28.3 - Coverage measured per group from the scored backfill `[CERT]`

`build_coverage_map(records)` keeps only realized records, buckets them by the `f"{symbol}|{tf}"` key, and
for each group runs `fc.calibration(recs)` and reads the `gaussian` reference model's `cover_90`, `cover_50`,
and `n` — the same primary cone model the verdict keys on (`REF_MODEL`)
(`analysis/cone_coverage.py:56-75`, `analysis/cone_coverage.py:32`) `[CERT]`. A group too thin to score a
band falls to `{"verdict": "insufficient"}` (`analysis/cone_coverage.py:68-70`) `[CERT]`. `[INFER]` Coverage
is thus measured on exactly the realized, out-of-sample forecast records — the same backfill the cones are
judged by elsewhere — so the flag inherits that evidence base rather than inventing its own.

## 28.4 - The warning is one line, and silent when honest `[CERT]`

`warning_line(symbol, tf, cmap)` returns the empty string for a `reliable` or `insufficient` verdict, a
`[!] COBERTURA ... BANDA ESTRECHA ... Dale mas margen` line for `too-tight`, and a softer `[i] COBERTURA ...
banda ANCHA (conservadora)` line for `too-wide` (`analysis/cone_coverage.py:116-126`) `[CERT]`; the lookup is
`coverage_verdict`, which returns `None` for an unknown symbol|tf so no warning is shown
(`analysis/cone_coverage.py:111-113`) `[CERT]`. `load_map` reads the emitted `corpus/cone-coverage.json` and
returns `{}` on any failure — absent map => no warnings (`analysis/cone_coverage.py:37-43`) `[CERT]`.
`[INFER]` The design is fail-quiet in BOTH directions: an unknown or reliable cone says nothing, and only a
band that demonstrably lied earns a printed line — so the warning carries signal, never noise.

## 28.5 - Wired into the live cone, right under the band `[CERT]`

In the live assessment, immediately after printing the Monte Carlo cone and the "deliver the BAND, never the
median" guidance, `analyze.py` imports `cone_coverage`, calls `warning_line(r["symbol"],
str(r["timeframe"]), load_map())`, and prints it when non-empty; a bare `except` keeps a missing module or
map from ever breaking the report (`analysis/analyze.py:315-323`) `[CERT]`. Directly below it, the
`realized_coverage` annotation reports the measured `cover_90`/`cover_50` for THIS forecast with the
instruction "read the band at its measured coverage" (`analysis/analyze.py:328-333`) `[CERT]`. `[INFER]` The
warning lands exactly where the user reads the P5/P95 numbers — the one place a too-tight band would
otherwise be trusted blindly — not buried in a separate calibration report.

## 28.6 - The numbers: only monthly gold is trustworthy `[CERT-live]`

The built map makes the metals case concrete: `OANDA:XAUUSD|D` cover_90 = 0.787 (n=47) too-tight,
`OANDA:XAUUSD|W` = 0.847 (n=59) too-tight, and only `OANDA:XAUUSD|M` = 0.911 (n=79) reliable — daily and
weekly gold under-cover by ~5-11 points while monthly delivers what it says
(`corpus/cone-coverage.json`, `sources/probes/cone-coverage-flag-session-2026-08-12.md`) `[CERT-live]`.
Silver echoes it (XAG|D 0.809 too-tight, XAG|W/M reliable), and the index cones lean the other way
(SPX500|D 0.957 too-wide) `[CERT-live]`. `[INFER]` The canonical case is metals at the short horizons:
DAILY and WEEKLY gold cones are the ones a trader must hand-widen, and monthly gold is the single metals cone
that can be read at face value — precisely the per-instrument texture the pooled 0.90 erased.

## 28.7 - Why a flag and not a correction `[INFER]`

`[INFER]` The obvious "fix" is to WIDEN the tight cones automatically, and this session proved that road is a
trap. Every auto-correction that tried it failed out-of-sample: the conformal 50%-band delta ([Block 20]) and
ACI ([Block 22]) both overfit at these sample sizes, and the block-bootstrap and vol-floor variants were
honest failures this session. The module says so in its own words — the honest fix is "NOT a conformal delta
(validated OOS as overfit at these sample sizes) but a FLAG"
(`analysis/cone_coverage.py:9-11`) `[CERT]`. The single-scalar widener tested this session was likewise
REJECTED OOS ([Block 30]); its plumbing survives only as an inert `[i] COBERTURA-K` note gated on a
`coverage_scalar_applied` field that the honest pipeline never sets
(`analysis/analyze.py:324-327`) `[CERT]`. `[INFER]` The standing posture: the cone is the toolkit's one
proven-valuable output, and telling the user WHERE it under-covers — so they widen the stop by hand — beats
silently shipping an OOS-fragile correction that would quietly reshape a band no better than the flag
describes it.

## 28.8 - Connections

- **[Block 20]** - the conformal 50%-band correction that overfit OOS; the flag is what this becomes instead
  of auto-correcting.
- **[Block 22]** - the ACI adaptive widener that failed the same way; the second auto-correction the flag
  deliberately refuses to be.
- **[Block 30]** - the single-scalar cone widener tested and REJECTED OOS this session; the flag stays
  diagnostic while the scalar plumbing is left inert.
- **[Block 15]** - per-market calibration ranking; the same per symbol|tf lens applied to which markets the
  edges hold in.
