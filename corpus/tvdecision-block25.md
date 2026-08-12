# Block 25 - Multi-timeframe directional bias: an honest up/down/flat + confidence tool

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> the directional-bias tool the user demanded ("si o si necesitamos ver si va para arriba o abajo").
> It reports a per-timeframe LEAN (up / down / flat) with an EXPLICIT confidence across 1m -> 1M,
> framed as a DESCRIPTIVE STATE — never a prediction. It is the honest counterpart to the zero-drift
> cones: the cones size the uncertainty, this tool names its sign but refuses to fake certainty.
>
> Subject version: `analysis/direction.py`, `analysis/direction.sh`, `analysis/direction_backfill.py`
> on branch `feat/quant-analysis-toolkit`. Session 2026-08-12.
>
> Sources: `analysis/direction.py`, `analysis/direction.sh`, `analysis/direction_backfill.py`
> (local primary source). Preserved run:
> `sources/probes/direction-tool-session-2026-08-12.md`. Git: `459c096` (multi-TF bias with
> confidence), `4003a9a` (walk-forward calibration), `47f5743` (reframe as descriptive state, stamp
> skill verdict).
> Method: read-only citation of authored code + a preserved live measurement. `[CERT]` marks a local
> `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> METHODOLOGY/DESIGN block. Rigor layer.

---

## 25.1 - The demand, and the honest design choice `[CERT]`

The user demanded a direction read; the cones (`analyze.py`) are deliberately ZERO-DRIFT and measure
only the SIZE of the uncertainty, not its sign — so they could not answer "up or down?" by design. This
module is the complement, and its docstring names the design decision outright: a per-timeframe LEAN
with an EXPLICIT confidence, "so a weak signal cannot pose as a strong one"
(`analysis/direction.py:5-16`) `[CERT]`. `[INFER]` The fork was between a naked arrow (a false promise)
and a descriptive state with honest confidence; the project chose the latter because it had already
validated (block bootstrap, 95 resolved forecasts) that trading the forecast direction had NO EDGE
intraday. The design refuses to fake certainty where none was ever measured.

## 25.2 - Directional content only from sign-carrying signals `[CERT]`

Every component that feeds a lean is reused verbatim from `quant.py` (single source of truth, already
unit-tested): OLS trend slope + HAC significance, rolling-regression regime label, Lo-MacKinlay variance
ratio, EMA50/EMA200 stack vs price, OBV slope, and RSI(14) distance from 50 as a mild tilt only
(`analysis/direction.py:18-26`, `analysis/direction.py:108-131`) `[CERT]`. Each becomes a weighted vote
in `[-1, 1]`: trend weight 2.0 (heavily discounted to 0.25 when the slope is not significant), regime
1.5, EMA stack 1.5 (0.75 half-vote when only EMA50 exists), OBV 1.0, RSI 0.5
(`analysis/direction.py:135-160`) `[CERT]`. `strength = |net_score| / total_weight` in `[0,1]`
(`analysis/direction.py:162-164`) `[CERT]`.

## 25.3 - Confidence is capped by a validated intraday-no-edge prior `[CERT]`

Confidence is `strength * sig_factor * vr_factor * tf_prior`, clipped at `CONF_CEIL = 0.95` so the tool
never claims certainty however aligned the votes are (`analysis/direction.py:166-178`) `[CERT]`. The
`TF_RELIABILITY` prior multiplies confidence DOWN by timeframe — 1m is quartered (0.25), 15m 0.45, D
0.90, W/M full weight — encoding the validated finding that the shorter the bar, the less a directional
read can be trusted (`analysis/direction.py:56-63`) `[CERT]`. Below `FLAT_STRENGTH = 0.15` or
`FLAT_CONFIDENCE = 0.20`, the read is sent to "flat" rather than a coin-flip arrow — the same idea as
`decide.py`'s Gate A refusing an insignificant trend (`analysis/direction.py:70-74`,
`analysis/direction.py:180-183`) `[CERT]`. `[INFER]` The real tradeable signal is ALIGNMENT: a lone 1m
arrow is small by construction, so only when higher timeframes agree does the agreement survive.

## 25.4 - Aggregate: alignment, weighted by confidence `[CERT]`

`aggregate` combines per-TF records into an overall lean by a confidence-weighted vote across
timeframes, and surfaces how many TFs actually agree (`n_up` / `n_down` / `n_flat`) plus the
higher-timeframe (D/W/M) consensus separately as the trustworthy part
(`analysis/direction.py:207-236`) `[CERT]`. Below `|agg| < 0.15` the overall is reported as
"flat/mixed" (`analysis/direction.py:226-229`) `[CERT]`. `[INFER]` Because each intraday confidence is
already small, a lone short-TF arrow cannot swing the verdict — the design makes alignment, not any
single row, the load-bearing signal.

## 25.5 - P(correct) is the REAL historical hit-rate, not the strength score `[CERT]`

`attach_calibration` adds `p_correct` = P(this call is correct) from the OOS-validated recalibration map
(`corpus/direction-calibration.json`), and the docstring is explicit that this is NOT the raw strength
score but "what the directional call has historically been worth OOS"; `bias`/`confidence` are left
untouched (`analysis/direction.py:268-287`) `[CERT]`. `[INFER]` This is the crux of the honesty
contract: `confidence` drives the flat/directional DECISION, while `p_correct` tells the reader what the
call has actually earned — a separation that stops a high-strength number from masquerading as a
probability of being right.

## 25.6 - The output stamps its own skill verdict and disclaims prediction `[CERT]`

The table header literally reads "DESCRIPTIVO — no es una prediccion (skill probado ~0/negativo)"
(`analysis/direction.py:298`) `[CERT]`. Each row is stamped with its per-TF skill tag from
`corpus/direction-skill.json` — `edge probado` / `sin skill` / `skill NEGATIVO` / `s/test`
(`analysis/direction.py:242-246`, `analysis/direction.py:311-313`) `[CERT]`, and confidences under 0.20
are annotated `-- ruido` (`analysis/direction.py:314-315`) `[CERT]`. The footer states plainly that no
TF beats the base-rate (12-symbol test), that 1H and monthly are NEGATIVE, and directs the reader to
size risk with the cones and treat the state as CONTEXT: "La direccion la decides tu, no el tool"
(`analysis/direction.py:331-338`) `[CERT]`. This is the reframe of commit `47f5743`.

## 25.7 - Multi-TF orchestration: locked, symbol-guarded, self-restoring `[CERT]`

`direction.sh` drives ONE symbol across 1m -> 1M. It holds the shared chart lock for its whole run via
`flock` on fd 9, so the background collect-hook cedes the live chart instead of cycling symbols under it
(`analysis/direction.sh:20-23`) `[CERT]`, cycling `TFS="M W D 60 15 1"` high -> low
(`analysis/direction.sh:27`) `[CERT]`. For each TF it pulls OHLCV with `--expect-symbol "$SYMBOL"`,
which refuses wrong-symbol bars from the hook's cycling and retries up to six times letting the feed
settle, rather than reading another market (`analysis/direction.sh:54-60`) `[CERT]` — the same
source-level guard documented in [Block 24]. An `EXIT` trap restores the starting symbol and resets the
timeframe to 15 on exit (`analysis/direction.sh:39-45`) `[CERT]`.

## 25.8 - The calibration generator: leakage-free walk-forward `[CERT]`

`direction_backfill.py` is what tests the confidence hypothesis rather than trusting the hand-chosen
`TF_RELIABILITY` prior (`analysis/direction_backfill.py:4-17`) `[CERT]`. It walks NON-OVERLAPPING
windows — the loop steps by `horizon` so each prediction is independent
(`analysis/direction_backfill.py:62`) `[CERT]` — and at each window end computes the bias from
`bars[:t+1]` ONLY, with no lookahead, pairing it against the realized direction at `t+h` already known
in history (`analysis/direction_backfill.py:49-78`) `[CERT]`. `calibrate` then reports the directional
hit-rate against the 0.50 coin-flip benchmark, a per-confidence-bin reliability diagram, and a Brier
score vs the 0.25 of always saying p=0.5 (`analysis/direction_backfill.py:82-121`) `[CERT]`. This is
commit `4003a9a`; it mirrors `backfill.py`'s cone-calibration discipline so the two share the same
gap-aware, non-overlapping method.

## 25.9 - The gold live run: a descriptive ALCISTA state, honestly stamped `[CERT-live]`

A live `bash analysis/direction.sh OANDA:XAUUSD` produced structure "2 alcista / 0 bajista / 4 plano",
overall ESTADO ESTRUCTURAL ALCISTA, with per-call P.acierto and skill stamps: 1 mes ^ up conf 0.94 /
74% hist / [skill NEGATIVO]; 1 dia ^ up conf 0.33 / 53% hist; the four intraday rows all flat and
tagged `-- ruido` (`sources/probes/direction-tool-session-2026-08-12.md:9-26`) `[CERT-live]`. `[INFER]`
The run is the design in action: the only up leans sit on the high timeframes, the monthly's proud 0.94
confidence is immediately undercut by its own 74%-hist and [skill NEGATIVO] stamps, and everything short
collapses to flat/ruido — the tool describes a bullish STRUCTURE while refusing to call it a forecast.

## 25.10 - Connections

- **[Block 26]** - the skill-significance test that PROVES this bias has no edge (no TF beats the
  base-rate; 1H and monthly negative). This block documents the TOOL; [Block 26] carries the proof and
  is not re-derived here.
- **[Block 5] / [Block 12]** - the zero-drift conformal cones, the SIZING counterpart. The cones measure
  the magnitude of uncertainty; this tool names its sign as context. The honest division of labor: size
  with the cones, read the state here, decide yourself.
