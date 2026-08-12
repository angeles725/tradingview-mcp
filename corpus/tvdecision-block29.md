# Block 29 - Lock-coordinated calibration refresh: one command, no chart race

> Research of the **TradingView trading analysis and decision methodology** (focus: `tvdecision`):
> the calibration artifacts (direction confidence/skill maps, cone coverage flag) are only as current
> as the data they were fit on. This documents the one-command, lock-coordinated, rate-limited refresh
> pipeline that rebuilds every derived artifact from fresh pulls, and the `flock` coordination that lets
> manual tools and the background collect-hook share the ONE live chart without racing.
>
> Subject version: `analysis/refresh-calibration.sh` + the shared `flock` in `analysis/collect-hook.sh`
> and `analysis/direction.sh`, on branch `feat/quant-analysis-toolkit`. Session 2026-08-12.
>
> Sources: `analysis/refresh-calibration.sh`, `analysis/collect-hook.sh`, `analysis/direction.sh`,
> and the produced artifacts `corpus/direction-calibration.json`, `corpus/direction-skill.json`,
> `corpus/cone-coverage.json`. Git commits `7449e10`, `85d76de`.
> Method: read-only citation of authored code + shape-read of the regenerated artifacts. `[CERT]`
> marks a local `file:line`; `[CERT-live]` a preserved live measurement; `[INFER]` an explicit deduction.
> INFRASTRUCTURE/HYGIENE block. Rigor layer.

---

## 29.1 - One chart, two writers, one race `[CERT]`

There is exactly one live TradingView chart on CDP `127.0.0.1:9222`, and two independent actors want to drive
it: the background `collect-hook` (fires on every Claude Code Stop event and cycles a 16-symbol basket) and
the foreground manual tools (`direction.sh`, `snapshot.sh`, and now `refresh-calibration.sh`). When the hook
switches the chart to another market mid-pull, a manual tool holding the chart gets handed the WRONG market's
bars. The `--expect-symbol` guard from [Block 24] REFUSES those wrong bars (`analysis/direction.sh:54-58`)
`[CERT]` — but refusing is not preventing: the tool still loses the pull and must retry
(commit `7449e10`: "guarded correctness but never prevented the race"). This block documents the mechanism
that PREVENTS the race, and the refresh tool that rides on it.

## 29.2 - A shared advisory lock every chart tool honors `[CERT]`

The coordination is one file, `analysis/data/.chart.lock`, taken via `flock` on fd 9 by every tool that
touches the chart. The pattern is identical across all three:

- `refresh-calibration.sh` takes it for its whole run: `exec 9>"$DATA/.chart.lock" ... && flock 9`
  (`analysis/refresh-calibration.sh:49`) `[CERT]`.
- `direction.sh` takes it for its whole run with the SAME idiom, fd 9 staying open until exit
  (`analysis/direction.sh:23`) `[CERT]`.
- `collect-hook.sh`, the background cycler, takes it too but with a TIMEOUT: `exec 9>'$DATA/.chart.lock'`
  then `if flock -w 8 9` (`analysis/collect-hook.sh:93-94`) `[CERT]`. If a manual tool already holds the
  lock, the hook CEDES the chart this tick and falls through to a store-only, score-only pass that needs no
  chart (`analysis/collect-hook.sh:109-111`) `[CERT]`; when it does hold the lock it releases it explicitly
  after restoring the primary chart (`flock -u 9`, `analysis/collect-hook.sh:108`) `[CERT]`.

`[INFER]` The asymmetry is the whole design: manual/refresh tools take the lock UNCONDITIONALLY (their pull
is the point), the background hook takes it with `-w 8` and yields on contention (its pull is opportunistic).
Whoever holds the advisory lock is the sole chart driver for the duration — so concurrent manual + hook use is
safe, not merely error-checked. Both tools also fail safe when `flock` is absent (`... || true`,
`analysis/refresh-calibration.sh:49`; commit `7449e10`) `[CERT]`.

## 29.3 - One pull feeds both backfills; the chart is restored on exit `[CERT]`

`refresh-calibration.sh` rebuilds TWO pools from the SAME fresh pulls rather than pulling twice. For each
symbol it seeds the direction pool from the accumulated store at 15m, pulls the intraday direction-only TFs
(1, 60), and then for each of D/W/M does ONE pull that feeds BOTH the direction backfill AND the cone backfill
(`analysis/refresh-calibration.sh:81-91`) `[CERT]`: a single `PULL_F` is piped into both
`direction_backfill.py` and `backfill.py` (`analysis/refresh-calibration.sh:84-85`) `[CERT]`. Every pull goes
through the same `--expect-symbol "$1"` guard with a 6-try settle loop (`analysis/refresh-calibration.sh:63`)
`[CERT]`, so the anti-race guard from [Block 24] protects the refresh too. On exit it restores the chart to
the symbol it started on and resets the timeframe to 15, via a `trap restore EXIT`
(`analysis/refresh-calibration.sh:51-53`) `[CERT]` — the same courtesy `direction.sh` extends
(`analysis/direction.sh:41-45`) `[CERT]`, so the refresh never leaves the user's chart on a foreign market.

## 29.4 - Rate-limited so it can be wired to a periodic hook `[CERT]`

A full refresh cycles a dozen symbols across five timeframes — too expensive to run every tick. So it is
gated by a stamp file `analysis/data/.last-refresh-calibration` and `REFRESH_MIN_AGE`, default `259200`
seconds = 3 days (`analysis/refresh-calibration.sh:31-32`) `[CERT]`. Unless `FORCE=1` is set, if the stamp is
younger than `REFRESH_MIN_AGE` it prints `refresh skipped` and exits 0 (`analysis/refresh-calibration.sh:37-42`)
`[CERT]`; the stamp is `touch`ed only after a successful pass (`analysis/refresh-calibration.sh:102`) `[CERT]`.
`[INFER]` This is the same self-throttling pattern the collect-hook uses for its own backfill seed
(`BACKFILL_MAX_AGE`, `analysis/collect-hook.sh:61,120-125`) `[CERT]` — a stamp + min-age makes a heavy job
safe to call unconditionally from a periodic hook, because it no-ops until the data is genuinely stale.

## 29.5 - The three artifacts it regenerates `[CERT]`

After the pulls, the tool regenerates every derived calibration artifact in one pass
(`analysis/refresh-calibration.sh:95-100`) `[CERT]`, and all three exist on disk with the expected shape:

- `corpus/direction-calibration.json` — per-timeframe confidence map: for each TF the sample count, up/down
  split, Brier scores (raw/marginal/isotonic), hit rate, chosen `method`, and whether it was `adopted`
  (e.g. `"15"`: n 84, hit 0.5714, method `marginal`, adopted; `"1"`: n 8, `adopted:false`, "insufficient
  evidence") (`corpus/direction-calibration.json:1-40`) `[CERT-live]`.
- `corpus/direction-skill.json` — per-timeframe skill significance: `verdict`, bootstrap skill vs benchmark,
  CI, p-value, n (e.g. `"60"`: verdict `negative`, skill -0.096; every reported TF is `no-skill`, `negative`,
  or `insufficient`) (`corpus/direction-skill.json:1-52`) `[CERT-live]`.
- `corpus/cone-coverage.json` — the per-instrument cone coverage flag from [Block 28]: keyed
  `SYMBOL|TF`, each with `cover_90`, `cover_50`, `n`, and a `verdict` of `too-tight` / `reliable` / `too-wide`
  (e.g. `OANDA:XAUUSD|D`: cover_90 0.787, `too-tight`; `OANDA:XAUUSD|M`: 0.911, `reliable`)
  (`corpus/cone-coverage.json:1-40`) `[CERT-live]`.

Regenerated via `direction_recalibrate.py`, `direction_significance.py` (with `--n-boot 3000`), and
`cone_coverage.py` respectively (`analysis/refresh-calibration.sh:95-100`) `[CERT]`.

## 29.6 - Why this is hygiene, not a model `[INFER]`

`[INFER]` Nothing here changes a forecast, a threshold, or a scoring rule — commit `85d76de` "consolidates
the session's ad-hoc calibration orchestration into a committed tool," it does not fit a new model. The value
is twofold and purely about keeping the existing calibration HONEST: (1) CURRENCY — the confidence maps, the
skill verdicts, and the coverage flags decay as the market drifts away from the data they were fit on, so a
rate-limited one-command rebuild keeps them current without a human remembering to; (2) UN-RACEDNESS — because
the rebuild pulls under the shared lock, the fresh data it fits on is guaranteed to be the RIGHT market's
bars, not a hand-off from the hook mid-cycle. A calibration artifact fit on stale or cross-contaminated data
would lie with the full authority of a "measured" number; this pipeline is the plumbing that stops that.

## 29.7 - Connections

- **[Block 24]** - the `--expect-symbol` source guard: the CORRECTNESS half of the anti-race defense (refuse
  wrong bars). The shared `flock` here is the PREVENTION half (don't race in the first place); the refresh
  pulls use both.
- **[Block 28]** - the per-instrument cone coverage flag (`cone-coverage.json`) that this pipeline refreshes.
- **[Block 25] / [Block 26]** - the direction confidence and skill maps
  (`direction-calibration.json`, `direction-skill.json`) that this pipeline refreshes.
