# Block 26 - Directional bias is a base-rate mirage: the definitive negative

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> the decisive negative on directional skill. Two independent methods — an OOS confidence
> recalibration and a significance test against the best CONSTANT predictor — agree that directional
> skill is ZERO or NEGATIVE at every timeframe. Beating 50% is not skill when the majority class is
> 57-63% up; the honest benchmark is the best constant predictor, and the bias never beats it. This
> block is the evidentiary basis that stamps [Block 25]'s tool DESCRIPTIVE and motivates the
> orthogonal-edge hunt [Block 27].
>
> Subject version: `analysis/direction_significance.py` + `analysis/direction_recalibrate.py` on
> branch `feat/quant-analysis-toolkit`. Session 2026-08-12.
>
> Sources: `analysis/direction_significance.py`, `analysis/direction_recalibrate.py` (local primary
> source). Preserved run:
> `corpus/sources/probes/directional-skill-negative-session-2026-08-12.md`. Git: 1400715 (OOS
> recalibration + honest P(correct) column), 997ef44 (skill significance test — no edge at any TF).
> Method: read-only citation of authored code + a preserved live measurement. `[CERT]` marks a local
> `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block. Rigor layer — the honesty bar of [Block 20]/[Block 22].

---

## 26.1 - The benchmark is the crux: skill = hit − best CONSTANT predictor `[CERT]`

Accuracy alone lies when one class dominates. `_benchmark` returns the accuracy of the best constant
predictor — always the majority realized class: `max(up, 1.0 - up)`
(`analysis/direction_significance.py:37-40`) `[CERT]`. The honest quantity is
`skill = hit_rate - benchmark` (`analysis/direction_significance.py:63`) `[CERT]`, not
`hit_rate - 0.5`. `[INFER]` This single choice retires the illusion: in a rising market where 57-63%
of moves are up, a naive "beat coin-flip 50%" bar rewards a permanently-long bias for merely echoing
the drift. Measuring against the best constant predictor strips that free base-rate credit away —
skill must exceed what "always up" already scores for nothing.

## 26.2 - Two independent nulls, neither of which the bias survives `[CERT]`

The test does not trust a point estimate. It runs two orthogonal nulls. (1) A CLUSTER BOOTSTRAP by
symbol resamples the 12 symbols with replacement — they share a macro regime, so per-window
resampling would understate variance — and reads a 95% CI on skill
(`analysis/direction_significance.py:67-79`) `[CERT]`. (2) A PERMUTATION shuffles predicted
directions against realized moves while preserving the up/down mix, giving
`p = P(random pairing >= observed accuracy)` (`analysis/direction_significance.py:81-86`) `[CERT]`.
Real edge requires BOTH: `real_skill = ci[0] > 0 and p_perm < 0.05`
(`analysis/direction_significance.py:88`) `[CERT]`; otherwise the output prints "SIN SKILL
demostrable" (`analysis/direction_significance.py:129`) `[CERT]`. The per-TF verdict is emitted as
re-testable DATA (`skill` / `no-skill` / `negative` / `insufficient`) via `build_skill_map`
(`analysis/direction_significance.py:100-122`) `[CERT]`, so [Block 25]'s tool can stamp the caveat
from the number, not from prose.

## 26.3 - The verdict at every timeframe: ZERO or NEGATIVE `[CERT-live]`

Pooled over `corpus/direction-cal-data.jsonl` (6448 records, 12 symbols), no timeframe demonstrates
skill (`corpus/sources/probes/directional-skill-negative-session-2026-08-12.md`) `[CERT-live]`:

| TF | n | mix | hit | benchmark | skill | perm p | verdict |
|----|----|-----|-----|-----------|-------|--------|---------|
| 15m | 84 | 84up/0dn | 57.1% | 57.1% | **+0.0%** | 1.000 | SIN SKILL |
| 60m | 198 | 155up/43dn | 51.0% | 60.6% | **−9.6%** | 0.973 | SIN SKILL |
| D | 279 | 210up/69dn | 52.7% | 53.0% | **−0.4%** | 0.387 | SIN SKILL |
| W | 438 | 306up/132dn | 54.6% | 58.7% | **−4.1%** | 0.342 | SIN SKILL |
| M | 549 | 397up/152dn | 55.6% | 59.2% | **−3.6%** | 0.259 | SIN SKILL |

Every timeframe reads SIN SKILL demostrable `[CERT-live]`. The best-looking cell — 60m at 51.0% hit —
is the WORST on skill: it trails a permanently-long predictor by 9.6 points, with p=0.973 that a
random pairing does at least as well. Not one TF clears the two-null bar of §26.2.

## 26.4 - The mirage, exposed: high-confidence subsets do NOT rescue it `[CERT-live]`

The obvious rebuttal — "the high-confidence calls carry the edge the population dilutes" — is
directly falsified. The tool re-runs each TF restricted to `confidence >= 0.6`, where the old
isotonic map claimed ~75% (`analysis/direction_significance.py:168-171`) `[CERT]`. Every such subset
is ALL-UP and skill collapses to exactly +0.0%: D[conf>=0.6] 33up/0dn hit 63.6% = benchmark 63.6%;
M[conf>=0.6] 122up/0dn hit 65.6% = benchmark 65.6%; W[conf>=0.6] 48up/1dn skill −2.0%
(`corpus/sources/probes/directional-skill-negative-session-2026-08-12.md`) `[CERT-live]`. `[INFER]`
This IS the base-rate mirage named. A high hit-rate at high confidence is not predictive power — it
is the tool being confident precisely when it is long, in a sample where longs happen to be the
majority class. Confidence tracks the up-rate, so "high confidence" and "majority class" are the same
subset wearing two labels; the hit-rate they share is the base rate, and skill over it is zero.

## 26.5 - The second, independent proof: recalibration flattens confidence to the base-rate `[CERT-live]`

The significance test asks "is there skill?"; the recalibration asks the orthogonal "does the
confidence number carry information?" — and answers no the same way. For each TF it fits three
candidates on a time-ordered 70/30 split (`analysis/direction_recalibrate.py:36`,`:74-89`) — `raw`
(trust the score), `marginal` (ignore it, output the base rate of correctness), `isotonic` — and
adopts the LOWEST out-of-sample Brier (`analysis/direction_recalibrate.py:91`) `[CERT]`. By
construction it can never ship worse than honestly collapsing to the base rate
(`analysis/direction_recalibrate.py:16-17`) `[CERT]`, and when `marginal` wins it prints "MARGINAL
(colapsa a base-rate)" (`analysis/direction_recalibrate.py:138`) `[CERT]`. Live, `marginal` wins at
15m, 60m and W — the raw confidence beat by a flat number equal to the up-rate — while D and M pick
`raw`/`isotonic` only because they too already sit at the base rate
(`corpus/sources/probes/directional-skill-negative-session-2026-08-12.md`) `[CERT-live]`. `[INFER]`
Two methods, one conclusion reached from opposite directions: the confidence→P(correct) map has no
slope worth keeping — it is the unconditional up-rate with noise on top.

## 26.6 - Why this is the definitive negative `[INFER]`

`[INFER]` Directional edge is retired, not merely "unconfirmed." The claim was tested against the
strongest honest null (best constant predictor), through two independent statistics (cluster
bootstrap CI + permutation p), at every timeframe, on a 12-symbol pool of 6448 records, and again by
an orthogonal OOS recalibration — and it failed every one, most damningly on its own high-confidence
subset. There is no remaining slice where "predict the direction" beats "assume the drift." This is
why [Block 25]'s tool is stamped DESCRIPTIVE: it may report a state, but it must not claim to
predict, because the data forbids the claim. And because a symmetric, correctly-benchmarked bias
carries zero information, any real edge must live in an ORTHOGONAL signal — the hunt [Block 27] takes
up. The honesty bar is the same one that produced the prior walk-forward negatives ([Block 20],
[Block 22]): a result is only "edge" when the CI excludes zero and p<0.05; a comfortable hit-rate
that merely rides the base rate is a mirage, and this block is the receipt.

## 26.7 - Connections

- **[Block 25]** - the directional tool this negative governs; stamped DESCRIPTIVE on this evidence.
- **[Block 27]** - the orthogonal-edge follow-up this zero-skill result motivates.
- **[Block 20]** / **[Block 22]** - prior walk-forward negatives held to the same honesty bar (CI excludes 0, p<0.05).
