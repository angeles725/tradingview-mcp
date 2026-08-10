# Block 11 - Multi-market forecast coverage: continuous-CFD expansion and the cash-index maturation boundary

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> extending the honest-forecast calibration loop beyond FX/metals/US to the Asian and European sessions,
> and the maturation boundary that separates continuous index CFDs (safe to auto-collect) from cash
> indices (safe only on demand, while live).
>
> Subject version: `analysis/collect-hook.sh` and `analysis/forecast.py` on branch
> `feat/quant-analysis-toolkit` (off `main`); recorded store `corpus/forecasts.jsonl`. Session 2026-08-10.
>
> Sources: `analysis/collect-hook.sh`, `analysis/forecast.py` (local primary source). Preserved run:
> `sources/probes/multi-market-forecast-session-2026-08-10.md`.
> Method: read-only citation of authored code plus a preserved in-session live run driven over CDP directly.
> `[CERT]` marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit
> deduction. METHODOLOGY/DESIGN block.
>
> Coverage layer. Broadens [Block 10]'s recurring feed across regions and records the one instrument class
> its "next-hour" cone cannot honestly serve unattended.

---

## 11.1 - Five markets, and why continuous CFDs `[CERT-live]` / `[INFER]`

The goal was calibration evidence across regions, not one session. Five markets were probed live over CDP
and each resolved to a 15m intraday series: China (`OANDA:CN50USD`), Europe (`OANDA:DE30EUR`, DAX),
US-tech (`OANDA:NAS100USD`), Japan (`OANDA:JP225USD`), and Korea (`KRX:KOSPI`)
(`sources/probes/multi-market-forecast-session-2026-08-10.md`) `[CERT-live]`. The four OANDA index CFDs
returned bars fresh to capture time (`period.to` ~now); KOSPI's newest bar was ~9.75 h stale with
`volume=0` on every bar. `[INFER]` The CFDs trade near-24h, so their bars are continuous the way FX is;
a cash index only prints during its exchange session, which is the whole reason the two are treated
differently downstream (11.3).

## 11.2 - The cone is horizon-in-BARS, and that is the trap `[CERT]`

`forecast.py record` sets the maturity time as `target_unix = made + step * horizon`
(`analysis/forecast.py:81`) - the forecast matures `horizon` BARS after the last bar, measured in bar-steps,
not wall-clock. On a continuous feed those two agree: 4 x 15m bars = the next hour. On a market that is
CLOSED, `made`/last-bar is stale, so `target_unix` is computed as 4 steps past a bar that has no successor
until the session reopens. `[INFER]` The projected "next hour" therefore lands INSIDE the overnight gap -
a timestamp at which no bar will ever print.

## 11.3 - KOSPI: an orphan record, confirmed not mis-scored `[CERT]` / `[CERT-live]`

For the KOSPI forecast, `target_unix = 1786347000` was already in the PAST at capture (~1786379096) yet
matured nothing (`sources/probes/multi-market-forecast-session-2026-08-10.md`) `[CERT-live]`. The scorer is
what makes this safe: `nearest_close` accepts a bar only within `tol = bar_step_sec // 2`
(`analysis/forecast.py:322`, `analysis/forecast.py:246`) - here 450 s. The distance from the target to the
newest KOSPI bar was 3600 s > 450, so `score --store` returned `scored 0` and did NOT match the stale last
bar `[CERT-live]`. `[INFER]` The tight tolerance prevents a wrong score, but it cannot rescue the record:
no bar will ever appear inside the gap, so the KOSPI forecast is a permanent orphan. Worse, the cone
under-states risk - it models 4 bars of intraday vol while the realized move spans a ~17 h overnight gap.

## 11.4 - The policy: auto-collect continuous, forecast cash on demand `[CERT]`

The `collect-hook.sh` symbol set was extended from the original six FX/metals/US instruments to ten, adding
the four continuous regional CFDs `CN50USD`/`DE30EUR`/`JP225USD`/`NAS100USD` (`analysis/collect-hook.sh:39`).
Cash indices such as `KRX:KOSPI` are INTENTIONALLY EXCLUDED from the auto-hook, with the reason recorded
inline: recorded near their close the h-bar target lands in the overnight gap, so the record never matures
and the cone under-states the true gap risk (`analysis/collect-hook.sh:35`). `[INFER]` The boundary is not
"OANDA vs native exchange" - it is CONTINUOUS vs SESSION-ONLY. A cash index can still be forecast manually
while its own market is live, where `made`/last-bar is current and the horizon stays inside the session.

## 11.5 - Data-quality note surfaced in passing: the dual gold key `[CERT-live]`

The store breakdown showed the same instrument under two symbol keys - `OANDA:XAUUSD` (19 records) and a
bare `XAUUSD` (7 records) - so `stats` with no `--symbol` reports 9/26 by summing both gold keys
(`sources/probes/multi-market-forecast-session-2026-08-10.md`) `[CERT-live]`. `[INFER]` The bare records
predate the `OANDA:`-prefix convention; symbol-exact scoring keeps them from cross-contaminating (the fix
from the cross-symbol work), but gold's calibration is split across two keys. Recorded as a known hygiene
item, not fixed in this session.

## 11.6 - What this adds and the standing limit `[INFER]`

This widens [Block 10]'s feed so [Block 8]'s decision loop accumulates calibration across the Asian,
European and US sessions instead of one region. It does not change any guardrail from [Block 5]/[Block 8]:
more regions sharpen coverage estimates, they do not make direction predictable. The new, explicit limit is
the maturation boundary - the "next-hour" cone is honest only on a CONTINUOUS feed; a cash index near its
close is out of the auto-loop by design.

## 11.7 - Connections

- **[Block 10]** - the recurring collection hook whose symbol set this extends.
- **[Block 8]** - the decision engine whose feedback loop these regions feed.
- **[Block 5]** - the honest-cone guardrails (vol, fat tails) the gap-risk caveat builds on.
- **[Block 9]** - the persistent store (`forecasts.jsonl`) where the dual-gold-key hygiene item lives.
