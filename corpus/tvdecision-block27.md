# Block 27 - Hunting orthogonal edge: the COT positioning probe finds none either

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> the edge-hunt's next move. After price-derived direction was proven no-skill ([Block 26]), the search
> left price entirely and went to NON-price data. A rolling COT positioning-extreme signal
> (commercial/speculator net) was built and tested for a directional edge on the SAME significance bar
> that killed momentum. Result: no edge — orthogonal data did not rescue direction.
>
> Subject version: `analysis/cot_probe.py` on branch `feat/quant-analysis-toolkit`. Session 2026-08-12.
>
> Sources: `analysis/cot_probe.py` (local primary source). Preserved run:
> `corpus/sources/probes/orthogonal-cot-session-2026-08-12.md`.
> Method: read-only citation of authored code + a preserved live+remote measurement. `[CERT]` marks a
> local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block. Rigor layer.

---

## 27.1 - Why leave price at all `[INFER]`

`[INFER]` [Block 26] proved every price-derived direction signal (momentum across timeframes) was
statistically no-skill under the permutation/cluster significance test. The natural next question is not
"a better price feature" but "is there ANY orthogonal signal that price cannot see?" COT (Commitments of
Traders) is genuinely orthogonal: it reports WHO is positioned, not what price did. The probe's own
docstring frames the thesis — commercials (hedgers, "smart money") at a positioning EXTREME lead the next
move — and commits to testing it "with the SAME machinery that killed the momentum edge — no double
standard" (`analysis/cot_probe.py:9`) `[CERT]`.

## 27.2 - The orthogonal source, fetched without auth `[CERT]`

The probe pulls the full weekly COT history from the CFTC Socrata endpoint `6dca-aqww`
(`analysis/cot_probe.py:40`) `[CERT]`, `fetch_cot` filtering by `market_and_exchange_names` over a plain
`urllib` GET with no API key (`analysis/cot_probe.py:43`) `[CERT]`. Per row it derives the commercial NET
= `comm_positions_long_all - comm_positions_short_all` (`analysis/cot_probe.py:61`) `[CERT]` — the
positioning quantity price never encodes. For the gold run the market string was
"GOLD - COMMODITY EXCHANGE INC." (`corpus/sources/probes/orthogonal-cot-session-2026-08-12.md:5`)
`[CERT-live]`.

## 27.3 - The signal: a rolling positioning extreme `[CERT]`

`cot_index` normalises the net into a rolling percentile (0..1) within a trailing window, NaN until the
window fills — trailing only, no lookahead (`analysis/cot_probe.py:69`) `[CERT]`. The window is a
156-week lookback (`analysis/cot_probe.py:128`) `[CERT]`. A directional call is emitted ONLY at an
extreme: index `>= 0.8` -> up, `<= 0.2` -> down, the middle skipped
(`analysis/cot_probe.py:129`, `analysis/cot_probe.py:130`) `[CERT]`; confidence scales with how far past
the threshold the index sits — the thesis says edge lives at the extremes. Realized direction is scored a
4-week horizon forward (`analysis/cot_probe.py:131`) `[CERT]` against weekly price closes read from stdin;
the probe refuses to run without them (`analysis/cot_probe.py:140`) `[CERT]`.

## 27.4 - Same bar, no double standard `[CERT]`

The probe does not invent its own scorer. It imports `direction_significance as sig`
(`analysis/cot_probe.py:38`) `[CERT]` — the exact module that killed the momentum edge in [Block 26] — and
runs `sig.skill_test` on the COT records (`analysis/cot_probe.py:155`) `[CERT]`, then re-runs it on the
high-extreme subset `conf>=0.5` because the thesis claims edge concentrates at the extremes
(`analysis/cot_probe.py:158`) `[CERT]`. Ship criterion, stated in the docstring, is identical to
everything else: skill CI > 0 AND permutation p < 0.05 (`analysis/cot_probe.py:22`) `[CERT]`.

## 27.5 - The measurement: worse than a coin, worse at the extremes `[CERT-live]`

The live gold run pulled 1928 COT rows against 400 weekly XAU price bars and produced 110 extreme signals
(28 up / 82 down). Full set: hit 32.7% vs a 63.6% always-majority benchmark -> SKILL = −30.9%, permutation
p = 0.997, verdict SIN SKILL. The high-extreme subset (`conf>=0.5`, n=58) did not rescue it — hit 34.5%
vs 60.3% -> SKILL = −25.9%, p = 0.989
(`corpus/sources/probes/orthogonal-cot-session-2026-08-12.md:8`) `[CERT-live]`. `[INFER]` The thesis
predicts the extreme subset should be the STRONGEST; instead it is negative and, in absolute-skill terms,
the whole set is worse still. The signal is not just absent — the extreme where it was supposed to
concentrate is if anything the worse place to look. A p near 1.0 means the observed anti-skill is entirely
consistent with noise; there is nothing here, not even an inverted edge to fade.

## 27.6 - An honest negative, recorded not hidden `[INFER]`

`[INFER]` This is committed as 67568cb ("COT positioning edge probe — orthogonal, still no edge") — the
negative is the deliverable, kept in the same lineage as [Block 26], not buried. It closes the
orthogonal-data avenue that [Block 26] opened. Other non-price sources were reachability-checked (FRED
macro, CFTC) but COT was the one actually BUILT and tested, and its negative is consistent with the
price-derived negative: with two independent data families — price-shape and positioning — both returning
no demonstrable skill on the same rigorous test, the working conclusion is that direction is not
forecastable from the data reachable here. Naming that plainly, rather than tuning thresholds until a
p-value flatters, is the point.

## 27.7 - Connections

- **[Block 26]** - the price-side no-skill result that motivated leaving price for orthogonal data; this
  block is its direct continuation and shares its significance machinery (`direction_significance`).
- **Edge-hunt lineage** - this is the current END of the edge-hunt lineage: price-derived direction (B26)
  and orthogonal COT positioning (here) both tested no-skill. No open avenue remains from the data
  reachable in this environment.
