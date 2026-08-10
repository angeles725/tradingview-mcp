# Block 8 - The decision engine: gated BUY / SELL / NO-TRADE, flat by default

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> how the whole toolkit composes into a single stance - BUY, SELL, or NO-TRADE - through three veto gates
> that default to flat, size trades by fixed risk, and NEVER place an order. Includes the walk-forward
> feedback mode that measures the process, not any single indicator.
>
> Subject version: `analysis/decide.py` committed `8e3247f` on branch `feat/quant-analysis-toolkit`
> (off `main` c05b8f5). Session 2026-08-05.
>
> Sources: `analysis/decide.py`, `analysis/test_decide.py` (local primary source). Preserved run:
> `sources/probes/decision-engine-session-2026-08-05.md`.
> Method: read-only citation of authored code plus a preserved live run over OANDA:XAUUSD 15m. `[CERT]`
> marks a local `file:line`; `[CERT-live]` a preserved live-feed measurement; `[CERT-hw]` a preserved test
> result; `[INFER]` an explicit deduction. METHODOLOGY/DESIGN block: a high `[INFER]`/`[CERT]` ratio is
> expected and healthy.
>
> Decision layer. Composes [Block 4] (trend/vol), [Block 5] (cone), [Block 6] (backtest), and [Block 7]
> (regime) into an actionable, honest stance.

---

## 8.1 - Safety by omission: the engine cannot place an order `[CERT]`

`decide.py` never imports the tv CLI, never calls `replay_trade`, and never contacts a broker; it reads
bars and prints a recommendation (`analysis/decide.py:6` states the contract; the module's imports are
only `quant` and `backtest`). `[INFER]` The safety is structural, not procedural - there is no code path
to an order, so it cannot regress into one. This honours the project's demo-before-real-money rule and the
default-denied `replay_trade` boundary from the capability-hardening focus.

## 8.2 - NO-TRADE by default; three veto gates `[CERT]`

`decide` (`analysis/decide.py:81`) returns NO-TRADE unless EVERY gate passes:

- **Gate A - direction** (`analysis/decide.py:97`): the trend must be statistically significant
  ([Block 4]), the current regime must align with the trend sign, and VR>1 must confirm momentum
  ([Block 7]). Otherwise there is no defensible direction (`analysis/decide.py:103`).
- **Gate B - edge** (`analysis/decide.py:110`): the rule in that direction must have a cost-surviving net
  edge - the backtest verdict must be `edge`, i.e. the bootstrap CI clears zero ([Block 6]). No validated
  edge, no trade (`analysis/decide.py:118`).
- **Gate C - risk/reward** (`analysis/decide.py:135`): stop at k*sigma (cone-scaled, [Block 5]), target at
  the cone's P75, and reward:risk at or above the threshold, else NO-TRADE (`analysis/decide.py:140`).

Only then is size set by a FIXED risk fraction over the stop distance
(`analysis/decide.py:143`) - never by conviction. `[INFER]` The ordering is deliberate: the cheapest,
most fundamental veto (is there even a direction?) runs first; the expensive backtest runs only if A
passes.

## 8.3 - Live: NO-TRADE, and exactly which gate blocked it `[CERT-live]`

On XAUUSD 15m the engine returned NO-TRADE at Gate A: the trend was significant (R^2=0.65) but the current
bar's regime was `chop`, not `trend-up`, so no entry was defensible
(`sources/probes/decision-engine-session-2026-08-05.md`). `[INFER]` This is the answer to "when do I NOT
trade": the engine names the failing gate, so the flat decision is explained, not merely asserted. Flat is
a position.

## 8.4 - Feedback: measure the PROCESS, not an indicator `[CERT]` / `[CERT-live]`

`simulate_process` (`analysis/decide.py:158`) walks the bars, applies the full decision at each step
(next-open fills, costs, no lookahead), and tallies the outcomes. To avoid re-bootstrapping Gate B every
bar (O(n^2)), it precomputes a single edge precondition on the in-sample half (`analysis/decide.py:168`) -
honest because a rule with no validated edge should keep the process flat throughout. Over 300 live bars
the process chose NO-TRADE on 100% of 238 evaluated bars and opened zero trades, because the in-sample
edge precondition was `thin-sample` `[CERT-live]`
(`sources/probes/decision-engine-session-2026-08-05.md`). `[INFER]` A 100%-flat result is the correct
outcome when there is no edge, but it is also weak FEEDBACK: with everything vetoed at Gate B, gates A and
C never vary, so their calibration is untested - which is exactly why more accumulated history ([Block 9])
is the enabling next step.

## 8.5 - Tests pin the gate logic `[CERT-hw]`

`analysis/test_decide.py` asserts chop vetoes at A, a forced no-edge vetoes at B, an impossible R:R vetoes
at C, a trending series with a forced edge and trivial R:R yields BUY, and sizing risks exactly the fixed
fraction (5/5 passing). `[CERT-hw]` (`sources/probes/decision-engine-session-2026-08-05.md`).

## 8.6 - Connections

- **[Block 4]/[Block 5]/[Block 6]/[Block 7]** - the components this engine composes.
- **[Block 9]** - the collector that grows history so Gate B can find real edges and the feedback loop
  becomes informative.
- **[Block 3]** - Replay practice is where a surviving stance earns trust before real money.
