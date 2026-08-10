# Block 15 - Which market forecasts best: a per-market calibration ranking

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> ranking the ten covered markets by how well the cone actually forecasts them — calibration honesty
> (coverage vs nominal) and sharpness (pinball) — to answer which market to trust and recommend.
>
> Subject version: `analysis/forecast.py` on branch `feat/quant-analysis-toolkit`; measured over the
> backfill log `corpus/forecasts-backfill.jsonl` (778 non-overlapping forecasts, new cone). Session
> 2026-08-10.
>
> Sources: `analysis/forecast.py` (local primary source). Preserved run:
> `sources/probes/market-ranking-session-2026-08-10.md`.
> Method: read-only citation of the scoring code plus a preserved in-session per-market measurement.
> `[CERT]` marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit
> deduction. METHODOLOGY/DESIGN block.
>
> Evidence layer. Turns [Block 12]'s per-model calibration and [Block 13]'s backfill into a per-MARKET
> recommendation.

---

## 15.1 - The two axes: honesty and sharpness `[CERT]`

A cone is judged on two things `calibration()` already computes: COVERAGE honesty (does the 90%/50% band
contain the realized close ~90%/~50% of the time) and SHARPNESS via the strictly-proper pinball loss
(`analysis/forecast.py:210`, `analysis/forecast.py:109`). `[INFER]` Coverage alone is gameable (a wider cone
always covers more), so the ranking pairs coverage with pinball — a tight cone that still covers is the
"best forecast", and pinball normalized to bps of price makes markets comparable.

## 15.2 - The per-market ranking `[CERT-live]`

Over the 778-forecast backfill (gaussian, n=62-126 per market), pinball_bps and coverage were
(`sources/probes/market-ranking-session-2026-08-10.md`) `[CERT-live]`:

| market | cov90 | cov50 | pin_bps | calErr |
|---|---|---|---|---|
| EURUSD | 0.94 | 0.64 | 1.16 | 0.18 |
| GBPUSD | 0.95 | 0.67 | 1.21 | 0.22 |
| AUDUSD | 0.94 | 0.59 | 1.59 | 0.13 |
| USDJPY | 0.95 | 0.58 | 2.10 | 0.13 |
| SPX500USD | 0.93 | 0.54 | 2.51 | 0.06 |
| DE30EUR (DAX) | 0.87 | 0.63 | 3.14 | 0.16 |
| CN50USD | 0.94 | 0.68 | 4.00 | 0.21 |
| NAS100USD | 0.92 | 0.73 | 4.79 | 0.25 |
| XAUUSD (gold) | 0.87 | 0.56 | 6.92 | 0.08 |
| JP225USD | 0.92 | 0.68 | 7.16 | 0.20 |

`calErr = |cov90-0.90| + |cov50-0.50|` (lower = more honest bands).

## 15.3 - The recommendation `[INFER]`

`[INFER]` **SPX500USD is the best-calibrated market** — both bands closest to nominal (calErr 0.06); when
its cone says 90% it means it. **EURUSD and GBPUSD have the sharpest cones** (pinball 1.16-1.21) and,
with tight spreads and 24h continuity, are the best to actually trade. So: trust SPX for the band, trade
the FX majors for sharpness + cost. This matches the three-agent methods survey (FX majors + a major US
index as Tier-1).

## 15.4 - Where NOT to trust the raw cone `[INFER]`

`[INFER]` **Gold (XAUUSD) and DAX (DE30EUR) are UNDER-covered at 90%** (0.87): their bands are too narrow
and UNDERSTATE risk — the [Block 11] gold-tail character. **Nasdaq/Nikkei/China over-disperse the 50% band**
(0.68-0.73). These are exactly the markets the [Block 13] conformal correction widens (gold/DAX) or tightens
(the 50% band), so their raw cones should be trusted least until the live conformal table accumulates.

## 15.5 - The honest caveat `[INFER]`

`[INFER]` A low pinball in FX is NOT superior skill — it reflects LOW relative volatility, so the cone is
naturally tighter because the instrument moves less. The ranking measures where the cone WORKS, which for
this probabilistic toolkit is the right question, but it is not a claim of directional edge (direction stays
~0.50, per [Block 5]). The numbers are backfill (historical, trailing-window fits), robust at n=62-126 but
not live forward coverage.

## 15.6 - Connections

- **[Block 12]** - the coverage/pinball calibration this ranks per market.
- **[Block 13]** - the backfill the ranking is measured over.
- **[Block 11]** - the gold-tail / under-coverage character confirmed here.
- **[Block 5]** - the "direction is ~unpredictable" stance the caveat rests on.
