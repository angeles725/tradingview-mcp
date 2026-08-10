"""
Quantitative analysis primitives for honest, range-based market assessment.

Design contract (do not violate):
  * NO function here predicts direction. Trend/vol/RSI refine SIZE and CONFIDENCE.
  * Every probabilistic output is a RANGE with an attached probability, never a
    single point forecast.
  * Small-sample results are flagged, not hidden.

Pure functions over numpy arrays so they stay unit-testable and reproducible.
Only numpy is required; scipy is used opportunistically (fat-tail fit, exact
binomial test) with graceful numeric fallbacks when it is absent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np

try:  # scipy is optional; every consumer degrades gracefully without it.
    from scipy import optimize, stats  # type: ignore
    _HAS_SCIPY = True
except Exception:  # pragma: no cover - exercised only on numpy-only hosts
    optimize = stats = None  # type: ignore
    _HAS_SCIPY = False


# --------------------------------------------------------------------------- #
# Returns
# --------------------------------------------------------------------------- #
def log_returns(closes: np.ndarray, times=None, gap_tol: float = 2.0) -> np.ndarray:
    """Per-bar log returns r_t = ln(C_t / C_{t-1}).

    If `times` (bar timestamps) is given, returns spanning a SESSION/OVERNIGHT
    GAP are dropped: a return whose bar interval exceeds `gap_tol` x the median
    interval is a multi-period jump, not a per-bar move, and would inflate sigma
    and corrupt GARCH/VR. Without `times` the behaviour is unchanged.
    """
    c = np.asarray(closes, dtype=float)
    r = np.diff(np.log(c))
    if times is None or r.size == 0:
        return r
    dt = np.diff(np.asarray(times, dtype=float))
    pos = dt[dt > 0]
    if pos.size == 0:
        return r
    step = float(np.median(pos))
    if step >= _INTRADAY_STEP_MAX:      # daily+ cadence: weekends/holidays are
        return r                         # normal bar boundaries, not session gaps
    return r[dt <= gap_tol * step]


# --------------------------------------------------------------------------- #
# Trend — OLS with significance, plus a robust cross-check
# --------------------------------------------------------------------------- #
@dataclass
class Trend:
    slope: float          # price units per bar (OLS)
    r2: float             # fraction of variance explained
    t_stat: float         # slope / SE(slope); |t|>~2 ~ significant
    ci95: tuple           # 95% confidence interval for the slope
    theilsen: float       # robust (outlier-resistant) slope, price/bar
    significant: bool     # CI excludes 0 AND r2 above noise floor
    n: int

    def as_dict(self):
        return asdict(self)


def newey_west_lrv(scores: np.ndarray, lag: int) -> float:
    """
    Newey-West HAC long-run variance of Sum(scores): gamma0 + 2*Sum Bartlett-
    weighted autocovariances up to `lag`. Accounts for serial correlation the
    i.i.d. sum-of-squares ignores. Clamped to gamma0 if the estimate goes
    non-positive (possible at tiny samples).
    """
    u = np.asarray(scores, dtype=float)
    n = u.size
    g0 = float(np.sum(u * u))
    s = g0
    for l in range(1, min(lag, n - 1) + 1):
        w = 1.0 - l / (lag + 1.0)
        s += 2.0 * w * float(np.sum(u[l:] * u[:-l]))
    return s if s > 0 else g0


def ols_trend(closes: np.ndarray, r2_floor: float = 0.30) -> Trend:
    """
    Fit price ~ a + b*t by least squares and report the slope WITH its
    statistical weight. A slope without R^2 and a confidence interval is the
    classic eyeballing mistake: report all three so a noisy line cannot pose
    as a trend.
    """
    y = np.asarray(closes, dtype=float)
    n = y.size
    x = np.arange(n, dtype=float)
    xm, ym = x.mean(), y.mean()
    sxx = np.sum((x - xm) ** 2)
    slope = np.sum((x - xm) * (y - ym)) / sxx
    intercept = ym - slope * xm
    yhat = intercept + slope * x
    resid = y - yhat
    ss_res = np.sum(resid ** 2)
    ss_tot = np.sum((y - ym) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Newey-West HAC standard error of the slope. Regressing a near-integrated
    # PRICE LEVEL on time yields strongly autocorrelated residuals, so the i.i.d.
    # SE = sqrt(sigma2/sxx) understates SE(slope) and inflates t (Granger-Newbold
    # spurious regression). The HAC sandwich uses the scores u_t = (x_t-xbar)*e_t.
    dof = max(n - 2, 1)
    if sxx > 0 and n > 2:
        lag = int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))   # Newey-West plug-in
        omega = newey_west_lrv((x - xm) * resid, lag)
        se_slope = math.sqrt(omega) / sxx
    else:
        se_slope = float("inf")
    t_stat = slope / se_slope if se_slope > 0 else 0.0
    tcrit = stats.t.ppf(0.975, dof) if _HAS_SCIPY else 1.96
    half = tcrit * se_slope
    ci95 = (slope - half, slope + half)

    theil = theilsen_slope(y)
    # bool(...) coerces numpy's np.bool_ (not a subclass of Python bool) so the
    # Trend serializes cleanly to JSON in analyze.py --json.
    significant = bool((ci95[0] > 0 or ci95[1] < 0) and r2 >= r2_floor)
    # HAC still can't rescue a level regression on an I(1) price: a random walk
    # yields a high-R^2 sloped line with zero true drift. Require the STATIONARY
    # drift (mean log-return) to be significant too — this restores the nominal
    # false-positive rate that the level-on-time test inflates (~60% -> ~5%).
    if significant and np.all(y > 0):
        rr = np.diff(np.log(y))
        m = rr.size
        sd = rr.std(ddof=1) if m > 1 else 0.0
        if m >= 3 and sd > 0:
            t_drift = rr.mean() / (sd / math.sqrt(m))
            tcrit_d = stats.t.ppf(0.975, m - 1) if _HAS_SCIPY else 1.96
            significant = bool(abs(t_drift) > tcrit_d)
        else:
            significant = False
    return Trend(slope, r2, t_stat, ci95, theil, significant, n)


def theilsen_slope(y: np.ndarray, max_pairs: int = 200_000, seed: int = 7) -> float:
    """
    Median of pairwise slopes — robust to outliers/spikes. Exact O(n^2) for a
    small series; once the number of pairs would exceed `max_pairs` (the collector
    grows history well past 300 bars) it SUBSAMPLES that many random index pairs,
    an unbiased estimate of the same median at bounded O(max_pairs) cost/memory.
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 2:
        return 0.0
    if n * (n - 1) // 2 <= max_pairs:
        i, j = np.triu_indices(n, k=1)
    else:
        rng = np.random.default_rng(seed)
        i = rng.integers(0, n, size=max_pairs)
        j = rng.integers(0, n, size=max_pairs)
        keep = i != j
        i, j = i[keep], j[keep]
    slopes = (y[j] - y[i]) / (j - i)
    return float(np.median(slopes))


def ema(closes: np.ndarray, period: int) -> np.ndarray:
    """
    Exponential moving average, aligned to `closes` with NaN for the warm-up.
    Seeded with the SMA of the first `period` bars (TradingView's convention),
    then smoothed with alpha = 2/(period+1).
    """
    c = np.asarray(closes, dtype=float)
    out = np.full(c.size, np.nan)
    if c.size < period:
        return out
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = c[:period].mean()
    for i in range(period, c.size):
        out[i] = alpha * c[i] + (1.0 - alpha) * out[i - 1]
    return out


def bootstrap_mean_ci(x: np.ndarray, n_boot: int = 10000,
                      alpha: float = 0.05, seed: int = 7) -> tuple:
    """
    Percentile bootstrap CI for the mean. Distribution-free — no normality
    assumption on the per-trade P&L, whose tails are fat and skewed. Returns
    (lo, hi); if the interval excludes 0 the mean edge is significant.

    NOTE: this is the i.i.d. bootstrap. It assumes the samples are independent;
    for a SERIALLY DEPENDENT series (raw returns, overlapping trades) use
    bootstrap_mean_ci_block, which preserves short-range dependence.
    """
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(n_boot, x.size))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def stationary_bootstrap_indices(n: int, m: int, expected_block: float,
                                 n_paths: int, rng) -> np.ndarray:
    """
    Politis-Romano (1994) stationary bootstrap index matrix, shape (n_paths, m).
    Each path is built from random-length contiguous blocks (geometric length,
    mean `expected_block`), wrapping around the series. Resampling BLOCKS instead
    of single points preserves short-range serial dependence — volatility
    clustering, momentum, mean reversion — that the i.i.d. bootstrap destroys.
    """
    if n == 0:
        return np.empty((n_paths, m), dtype=int)
    p = 1.0 / max(expected_block, 1.0)     # per-step restart probability
    out = np.empty((n_paths, m), dtype=int)
    for pth in range(n_paths):
        i = int(rng.integers(0, n))
        for t in range(m):
            out[pth, t] = i
            if rng.random() < p:
                i = int(rng.integers(0, n))    # start a new block
            else:
                i = (i + 1) % n                 # continue the current block
    return out


def bca_ci(boot: np.ndarray, theta_hat: float, jackknife: np.ndarray,
           alpha: float = 0.05) -> tuple:
    """
    BCa (bias-corrected accelerated) interval endpoints from bootstrap replicates
    `boot`, the point estimate `theta_hat`, and leave-one-out `jackknife` values.
    The plain percentile bootstrap UNDER-covers for skewed statistics (per-trade
    P&L is skewed/fat-tailed); BCa corrects for median bias (z0) and skewness
    (acceleration a). Falls back to plain percentiles without scipy.
    """
    b = np.asarray(boot, dtype=float)
    if b.size == 0:
        return (float("nan"), float("nan"))
    if not _HAS_SCIPY:
        lo, hi = np.percentile(b, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        return (float(lo), float(hi))
    prop = float(np.clip(np.mean(b < theta_hat), 1e-6, 1 - 1e-6))
    z0 = stats.norm.ppf(prop)
    j = np.asarray(jackknife, dtype=float)
    diff = j.mean() - j
    s2 = float(np.sum(diff ** 2))
    a = float(np.sum(diff ** 3) / (6.0 * s2 ** 1.5)) if s2 > 0 else 0.0

    def _pct(z):
        val = z0 + (z0 + z) / (1.0 - a * (z0 + z))
        return 100.0 * float(stats.norm.cdf(val))

    lo, hi = np.percentile(b, [_pct(stats.norm.ppf(alpha / 2)),
                               _pct(stats.norm.ppf(1 - alpha / 2))])
    return (float(lo), float(hi))


def bootstrap_mean_ci_block(x: np.ndarray, expected_block: float = 10.0,
                            n_boot: int = 5000, alpha: float = 0.05,
                            seed: int = 7) -> tuple:
    """
    Stationary-bootstrap CI for the mean of a SERIALLY DEPENDENT series, with a
    BCa correction. Wider (more honest) than the i.i.d. CI when the data are
    autocorrelated — it does not pretend neighbouring samples are independent —
    and BCa additionally corrects the skew/median-bias under-coverage of the
    plain percentile interval.
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    if n == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = stationary_bootstrap_indices(n, n, expected_block, n_boot, rng)
    means = x[idx].mean(axis=1)
    if not _HAS_SCIPY or n < 3:
        lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        return (float(lo), float(hi))
    jack = (n * x.mean() - x) / (n - 1)          # leave-one-out jackknife of the mean
    return bca_ci(means, float(x.mean()), jack, alpha)


# --------------------------------------------------------------------------- #
# Regime — is the series trending or mean-reverting? A trend rule that looks
# good only inside a trend is not an edge; regime tells you when to trust it.
# --------------------------------------------------------------------------- #
# A bar cadence at or above one day is daily+/weekly: weekend and holiday
# "gaps" are the normal spacing between bars, not intraday session gaps to
# exclude. The gap-awareness (built for intraday) is disabled at/above this.
_INTRADAY_STEP_MAX = 86400.0            # seconds (1 day)


def _gap_keep_mask(times, gap_tol: float = 2.0):
    """Boolean mask over the per-bar RETURNS array (len = len(times)-1): True where the
    return is WITHIN-SESSION. A return whose interval exceeds gap_tol x the median step
    is a session/overnight jump and is dropped. On a daily+ cadence there are no intraday
    gaps, so all returns are kept. Mirrors the log_returns gap filter so the barrier
    resample pool matches the gap-clean cone."""
    dt = np.diff(np.asarray(times, dtype=float))
    pos = dt[dt > 0]
    if pos.size == 0:
        return np.ones(dt.size, dtype=bool)
    step = float(np.median(pos))
    if step >= _INTRADAY_STEP_MAX:      # daily+ cadence: no session-gap fragmentation
        return np.ones(dt.size, dtype=bool)
    return dt <= gap_tol * step


def _return_segments(times, gap_tol: float = 2.0):
    """Index ranges (s,e) into the RETURNS array (len = len(times)-1) of consecutive
    WITHIN-SESSION returns. A return spanning a time gap (dt > gap_tol*median step)
    is a boundary, so overlapping k-sums never stitch across a session gap. On a
    daily+ cadence there are no intraday gaps to split, so the whole series is one
    segment."""
    t = np.asarray(times, dtype=float)
    dt = np.diff(t)
    pos = dt[dt > 0]
    if pos.size == 0:
        return [(0, dt.size)]
    step = float(np.median(pos))
    if step >= _INTRADAY_STEP_MAX:      # daily+ cadence: no session-gap fragmentation
        return [(0, dt.size)]
    valid = dt <= gap_tol * step
    segs, s = [], None
    for i, v in enumerate(valid):
        if v and s is None:
            s = i
        elif not v and s is not None:
            segs.append((s, i)); s = None
    if s is not None:
        segs.append((s, valid.size))
    return segs


def _ksums(r: np.ndarray, k: int, segs=None):
    """Overlapping k-bar sums, pooled WITHIN contiguous segments when `segs` given."""
    if segs is None:
        cs = np.cumsum(r)
        return cs[k - 1:] - np.concatenate(([0.0], cs[:-k]))
    out = []
    for s, e in segs:
        seg = r[s:e]
        if seg.size >= k:
            cs = np.cumsum(seg)
            out.append(cs[k - 1:] - np.concatenate(([0.0], cs[:-k])))
    return np.concatenate(out) if out else np.empty(0)


def variance_ratio(returns: np.ndarray, k: int, times=None, gap_tol: float = 2.0) -> float:
    """
    Lo-MacKinlay variance ratio VR(k) = Var(k-bar return) / (k * Var(1-bar
    return)), overlapping estimator. VR ~ 1 random walk; VR > 1 positive serial
    correlation (trending/momentum); VR < 1 mean reversion. When `times` (bar
    timestamps aligned to `returns`) is given, k-sums are pooled only WITHIN
    contiguous sessions so they never straddle a dropped gap.
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    if n < k + 1 or k < 1:
        return float("nan")
    segs = _return_segments(times, gap_tol) if times is not None else None
    # var1 (denominator) must be measured over the SAME within-session population
    # as the k-sum numerator; including the excluded cross-gap returns would
    # inflate var1 and deflate VR on gapped instruments.
    seg_r = np.concatenate([r[s:e] for s, e in segs]) if segs is not None else r
    if seg_r.size < 2:
        return float("nan")
    var1 = np.var(seg_r, ddof=1)
    if var1 == 0:
        return float("nan")
    ksum = _ksums(r, k, segs)
    if ksum.size < 2:
        return float("nan")
    vark = np.var(ksum, ddof=1)
    return float(vark / (k * var1))


def barrier_hit_probabilities(entry: float, o: np.ndarray, h: np.ndarray,
                              l: np.ndarray, c: np.ndarray, horizon: int,
                              stop: float, target: float, direction: int = 1,
                              drift_zero: bool = True, n: int = 20000,
                              seed: int = 7, expected_block: float = 5.0,
                              times=None, gap_tol: float = 2.0) -> dict:
    """
    Monte-Carlo FIRST-PASSAGE probabilities with INTRABAR extremes: over `horizon`
    bars, which barrier (target or stop) is touched FIRST. Resamples historical
    bars jointly as (close return, high excursion, low excursion) via the STATIONARY
    BLOCK bootstrap, so the paths inherit the serial dependence (momentum) that Gate
    A requires — an i.i.d. resample would erase it. Intrabar touches count; a bar
    spanning both barriers is charged to the STOP (conservative). Returns
    p_target/p_stop/p_neither.
    """
    c = np.asarray(c, dtype=float)
    if c.size < 2 or horizon < 1:
        return {"p_target": float("nan"), "p_stop": float("nan"), "p_neither": float("nan"), "n": 0}
    prev = c[:-1]
    rc = np.log(c[1:] / prev)                         # close-to-close return
    hi = np.log(np.asarray(h, float)[1:] / prev)      # high excursion vs prev close
    lo = np.log(np.asarray(l, float)[1:] / prev)      # low excursion vs prev close
    if times is not None:
        # Drop cross-session bars from the resample pool BEFORE the drift is measured,
        # so both the drift (mu) and the path dispersion match the gap-clean cone that
        # sets the target — otherwise overnight gaps inflate p_target / understate p_stop.
        keep = _gap_keep_mask(times, gap_tol)
        rc, hi, lo = rc[keep], hi[keep], lo[keep]
    if drift_zero:
        mu = rc.mean()
        rc, hi, lo = rc - mu, hi - mu, lo - mu        # shift the whole bar by its drift
    m = rc.size
    if m == 0:
        return {"p_target": float("nan"), "p_stop": float("nan"), "p_neither": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    idx = stationary_bootstrap_indices(m, horizon, expected_block, n, rng)
    close_end = np.cumsum(rc[idx], axis=1)            # close level at END of each bar
    start = close_end - rc[idx]                       # level at START of each bar
    price_high = entry * np.exp(start + hi[idx])
    price_low = entry * np.exp(start + lo[idx])
    if direction > 0:
        hit_t, hit_s = price_high >= target, price_low <= stop
    else:
        hit_t, hit_s = price_low <= target, price_high >= stop

    def _first(mask):
        idx_ = np.argmax(mask, axis=1)
        idx_[~mask.any(axis=1)] = horizon             # no hit -> sentinel past the end
        return idx_

    it, istop = _first(hit_t), _first(hit_s)
    both_same = (it == istop) & (it < horizon)        # bar spans both -> charge to stop
    p_stop = float(np.mean((istop < it) | both_same))
    p_target = float(np.mean(it < istop))
    return {"p_target": p_target, "p_stop": p_stop,
            "p_neither": float(1.0 - p_target - p_stop), "n": int(n)}


def max_drawdown(returns: np.ndarray) -> float:
    """Maximum peak-to-trough drawdown as a FRACTION, from per-trade log returns.
    Expectancy hides path risk: two rules with equal mean can have wildly
    different drawdowns, and drawdown is what ends accounts."""
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    # Seed the path with the opening level (log-equity 0) so the initial capital
    # is the first high-water mark: a losing first trade is a real drawdown, not 0.
    eq = np.concatenate(([0.0], np.cumsum(r)))   # cumulative log return from start
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - np.exp(eq - peak)            # fractional drawdown at each step
    return float(np.max(dd)) if dd.size else 0.0


def probabilistic_sharpe(returns: np.ndarray, benchmark: float = 0.0) -> float:
    """
    Bailey-Lopez de Prado Probabilistic Sharpe Ratio: P(true Sharpe > benchmark)
    given the observed Sharpe, sample size, skew and kurtosis. Unlike the raw
    Sharpe it penalises short samples and fat left tails, so a lucky high Sharpe
    on few, skewed trades no longer looks certain. Returns a probability in [0,1].
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    if n < 3:
        return float("nan")
    sd = r.std(ddof=1)
    if sd <= 0:
        return float("nan")
    sr = r.mean() / sd
    m = r - r.mean()
    s2 = float(np.mean(m * m))
    if s2 <= 0:
        return float("nan")
    skew = float(np.mean(m ** 3)) / s2 ** 1.5
    kurt = float(np.mean(m ** 4)) / (s2 * s2)          # non-excess (normal = 3)
    denom = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    if denom <= 0 or not np.isfinite(denom):
        return float("nan")
    z = (sr - benchmark) * math.sqrt(n - 1) / math.sqrt(denom)
    return float(stats.norm.cdf(z)) if _HAS_SCIPY else float("nan")


def variance_ratio_test(returns: np.ndarray, k: int, times=None,
                        gap_tol: float = 2.0) -> tuple:
    """
    Lo-MacKinlay (1988) variance ratio with the HETEROSKEDASTICITY-ROBUST M2
    z-statistic. Returns (vr, z, p_two_sided). Under H0 (no serial correlation)
    z ~ N(0,1); z>0 means VR>1 (momentum), z<0 mean reversion. When `times` is
    given, the VR and the autocovariance sums are computed WITHIN contiguous
    sessions only, so a dropped gap is never stitched across.
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    if n < k + 1 or k < 2:
        return (float("nan"), float("nan"), float("nan"))
    vr = variance_ratio(r, k, times=times, gap_tol=gap_tol)
    segs = _return_segments(times, gap_tol) if times is not None else [(0, r.size)]
    # Demean and normalise over within-session returns only (the same population
    # the segmented autocovariance sums use); the excluded cross-gap returns must
    # not enter the mean or S, or they contaminate the z-statistic.
    seg_r = np.concatenate([r[s:e] for s, e in segs]) if segs else np.empty(0)
    if seg_r.size < 2 or not np.isfinite(vr):
        return (vr, float("nan"), float("nan"))
    d = r - seg_r.mean()                       # aligned to r for segment slicing
    d2 = d * d
    S = float(np.sum([float(np.sum(d2[s:e])) for s, e in segs]))
    if S <= 0:
        return (vr, float("nan"), float("nan"))
    # theta*(k) = sum_{j=1}^{k-1} [2(k-j)/k]^2 * delta_j ,  delta_j = Σ d2_t d2_{t-j} / (Σ d2)^2
    # with the lagged products summed only WITHIN each contiguous segment.
    theta = 0.0
    for j in range(1, k):
        num = 0.0
        for s, e in segs:
            seg = d2[s:e]
            if seg.size > j:
                num += float(np.sum(seg[j:] * seg[:-j]))
        delta_j = num / (S * S)
        w = 2.0 * (k - j) / k
        theta += (w * w) * delta_j
    if theta <= 0 or not np.isfinite(theta):
        return (vr, float("nan"), float("nan"))
    z = (vr - 1.0) / math.sqrt(theta)
    p = float(2.0 * (1.0 - stats.norm.cdf(abs(z)))) if _HAS_SCIPY else float("nan")
    return (float(vr), float(z), p)


def classify_regime(closes: np.ndarray, window: int = 20,
                    r2_floor: float = 0.30) -> np.ndarray:
    """
    Per-bar regime label from a rolling linear regression: 'trend-up',
    'trend-down', or 'chop'. A bar is trending only when the window R^2 clears
    the noise floor; otherwise it is chop. The warm-up bars are 'chop' by
    default (no window yet). Aligned to `closes`.
    """
    c = np.asarray(closes, dtype=float)
    n = c.size
    labels = np.array(["chop"] * n, dtype=object)
    x = np.arange(window, dtype=float)
    xm = x.mean()
    sxx = np.sum((x - xm) ** 2)
    for t in range(window - 1, n):
        y = c[t - window + 1:t + 1]
        ym = y.mean()
        slope = np.sum((x - xm) * (y - ym)) / sxx
        yhat = ym + slope * (x - xm)
        ss_res = np.sum((y - yhat) ** 2)
        ss_tot = np.sum((y - ym) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        if r2 >= r2_floor:
            labels[t] = "trend-up" if slope > 0 else "trend-down"
    return labels


# --------------------------------------------------------------------------- #
# Volatility — several estimators, because close-to-close wastes OHLC and
# assumes constant variance. Report per-bar sigma; scale downstream.
# --------------------------------------------------------------------------- #
def close_to_close_vol(returns: np.ndarray) -> float:
    """Plain stdev of log returns (sample). Baseline, noisiest estimator."""
    r = np.asarray(returns, dtype=float)
    return float(np.std(r, ddof=1))


def ewma_vol(returns: np.ndarray, lam: float = 0.94, warmup: int = 10) -> float:
    """
    RiskMetrics EWMA (an IGARCH). Weights recent bars more, so it tracks
    volatility CLUSTERING and returns the *current-conditional* sigma rather
    than a flat historical average. lam=0.94 is the RiskMetrics daily default.

    Seeded with the mean squared return over a warm-up window. The recursion is
    uncentered (it tracks E[r^2]), so the seed is the same uncentered moment,
    NOT the centered sample variance — using a single r[0]^2 is a very noisy seed
    whose error biases the early conditional sigma.
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    if n == 0:
        return 0.0
    w = min(max(warmup, 1), n)
    var = float(np.mean(r[:w] ** 2))
    for x in r[w:]:
        var = lam * var + (1.0 - lam) * x * x
    return float(math.sqrt(var))


def parkinson_vol(high: np.ndarray, low: np.ndarray) -> float:
    """
    Parkinson (1980) range estimator. Uses the high-low range, which carries
    far more information than the close alone -> lower-variance sigma. Assumes
    no drift and continuous sampling (slightly biased low with gaps).
    """
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    hl = np.log(h / l)
    factor = 1.0 / (4.0 * math.log(2.0))
    return float(math.sqrt(factor * np.mean(hl ** 2)))


def garman_klass_vol(o, h, l, c) -> float:
    """
    Garman-Klass (1980). Combines the OHLC range and the open-close move; the
    most efficient of the classic estimators (~7-8x the information of
    close-to-close), best when there is little overnight gapping.
    """
    o = np.asarray(o, dtype=float); h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float); c = np.asarray(c, dtype=float)
    hl = np.log(h / l)
    co = np.log(c / o)
    var = 0.5 * hl ** 2 - (2.0 * math.log(2.0) - 1.0) * co ** 2
    return float(math.sqrt(np.mean(var)))


def rogers_satchell_var(o, h, l, c) -> np.ndarray:
    """Rogers-Satchell (1991) per-bar variance proxy. Unlike Garman-Klass it is
    drift-INDEPENDENT (valid when the bar has a trend), and it is non-negative by
    construction. Returned per bar so it can seed a realized-variance series for
    HAR (each term is an intraday range, so overnight gaps never contaminate it).
    """
    o = np.asarray(o, dtype=float); h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float); c = np.asarray(c, dtype=float)
    return np.log(h / c) * np.log(h / o) + np.log(l / c) * np.log(l / o)


def yang_zhang_vol(o, h, l, c) -> float:
    """Yang-Zhang (2000) per-bar sigma. Minimum-variance among unbiased OHLC
    estimators and the only classic one that handles OVERNIGHT GAPS correctly:
    sigma^2 = Vo + k*Vc + (1-k)*Vrs, combining overnight (close->open), open->close,
    and the drift-free Rogers-Satchell term. Falls back to Garman-Klass when there
    are too few bars for the overnight-variance term.
    """
    o = np.asarray(o, dtype=float); h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float); c = np.asarray(c, dtype=float)
    n = c.size
    if n < 2:
        return 0.0
    co = np.log(o[1:] / c[:-1])          # overnight (close_{t-1} -> open_t)
    oc = np.log(c / o)                   # open -> close (same bar)
    rs = rogers_satchell_var(o, h, l, c)
    v_o = float(np.var(co, ddof=1)) if co.size > 1 else 0.0
    v_c = float(np.var(oc, ddof=1)) if oc.size > 1 else 0.0
    v_rs = float(np.mean(rs))
    k = 0.34 / (1.34 + (n + 1.0) / (n - 1.0))
    var = v_o + k * v_c + (1.0 - k) * v_rs
    return float(math.sqrt(var)) if var > 0 else 0.0


def garch11_vol(returns: np.ndarray):
    """
    Fit a GARCH(1,1) with STUDENT-t innovations and return the one-step-ahead
    conditional sigma. Real returns are fat-tailed, so Gaussian MLE biases the
    alpha/beta estimates; a t likelihood (df estimated) is the honest choice.
    Uses VARIANCE TARGETING (omega = var*(1-alpha-beta)) to drop a parameter and
    MULTIPLE STARTS for optimiser robustness. Returns (sigma, params) — params
    includes nu — or None if scipy is absent / the fit fails; callers fall to EWMA.
    """
    if not _HAS_SCIPY:
        return None
    r = np.asarray(returns, dtype=float)
    r = r - r.mean()
    var0 = float(np.var(r))
    if var0 <= 0 or r.size < 10:
        return None

    def sigma2_path(alpha, beta):
        omega = var0 * (1.0 - alpha - beta)          # variance targeting
        s2 = np.empty_like(r)
        s2[0] = var0
        for t in range(1, r.size):
            s2[t] = omega + alpha * r[t - 1] ** 2 + beta * s2[t - 1]
        return s2, omega

    def nll_t(theta):
        alpha, beta, nu = theta
        if alpha < 0 or beta < 0 or alpha + beta >= 0.999 or nu <= 2.05 or nu > 200:
            return 1e12
        s2, _ = sigma2_path(alpha, beta)
        if np.any(s2 <= 0) or not np.all(np.isfinite(s2)):
            return 1e12
        # variance-standardized Student-t (Var=sigma^2 via the (nu-2) scaling)
        c = math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - 0.5 * math.log(math.pi * (nu - 2))
        ll = c - 0.5 * np.log(s2) - ((nu + 1) / 2) * np.log(1.0 + r ** 2 / ((nu - 2) * s2))
        return -float(np.sum(ll))

    best = None
    for x0 in ((0.05, 0.90, 8.0), (0.10, 0.85, 5.0), (0.03, 0.95, 12.0)):
        try:
            res = optimize.minimize(nll_t, np.array(x0), method="Nelder-Mead",
                                    options={"maxiter": 4000, "xatol": 1e-8, "fatol": 1e-8})
        except Exception:
            continue
        if np.isfinite(res.fun) and (best is None or res.fun < best.fun):
            best = res
    if best is None:
        return None
    alpha, beta, nu = best.x
    if alpha < 0 or beta < 0 or alpha + beta >= 1 or nu <= 2:
        return None
    omega = var0 * (1.0 - alpha - beta)
    sigma2 = var0
    for t in range(1, r.size):
        sigma2 = omega + alpha * r[t - 1] ** 2 + beta * sigma2
    sigma_next = omega + alpha * r[-1] ** 2 + beta * sigma2
    if sigma_next <= 0 or not np.isfinite(sigma_next):
        return None
    return math.sqrt(sigma_next), {"omega": float(omega), "alpha": float(alpha),
                                   "beta": float(beta), "nu": float(nu)}


def scale_sigma(sigma_bar: float, horizon: int, vr: float = 1.0) -> float:
    """Scale per-bar sigma to an N-bar horizon, honoring the variance ratio.

    Under a random walk Var(h-bar) = h * sigma^2, i.e. sqrt(h). But with serial
    correlation Var(h-bar) ~ VR(h) * h * sigma^2, so sigma_h = sigma * sqrt(h*VR).
    Since the engine only trades when VR>1, plain sqrt(h) understates horizon
    volatility exactly in the trading regime. A degenerate VR (NaN or <=0) falls
    back to random-walk scaling rather than propagating NaN.
    """
    if vr is None or not math.isfinite(vr) or vr <= 0:
        vr = 1.0
    return sigma_bar * math.sqrt(horizon * vr)


def har_rv_forecast(rv: np.ndarray, windows=(1, 5, 22)) -> float:
    """One-step-ahead realized-VARIANCE forecast via Corsi's (2009) HAR model.

    HAR regresses next-period RV on trailing averages over three timescales
    (short/medium/long) — the most consistently dominant out-of-sample volatility
    model in the literature. `rv` is a per-bar realized-variance series (e.g.
    Rogers-Satchell), so it is gap-robust. Features for target t are the trailing
    means ENDING BEFORE t (strictly causal, no look-ahead). Falls back to the mean
    RV when the series is shorter than the longest window, and clamps a degenerate
    (non-finite or non-positive) fit back to that mean.
    """
    rv = np.asarray(rv, dtype=float)
    n = rv.size
    w_max = max(windows)
    mean_rv = float(np.mean(rv)) if n else 0.0
    if n <= w_max:                       # too short for a causal HAR design
        return mean_rv
    rows, targets = [], []
    for t in range(w_max, n):
        rows.append([float(np.mean(rv[t - w:t])) for w in windows])
        targets.append(rv[t])
    X = np.column_stack([np.ones(len(rows)), np.array(rows)])
    y = np.array(targets)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    feat_next = np.array([1.0] + [float(np.mean(rv[n - w:n])) for w in windows])
    pred = float(feat_next @ coef)
    if not math.isfinite(pred) or pred <= 0.0:
        return mean_rv
    return pred


def blend_sigma(*sigmas, weights=None) -> "float | None":
    """Equal-weight (or `weights`-weighted) blend of several per-bar sigmas,
    skipping None / non-finite operands. Used to combine the GARCH conditional
    sigma with the HAR-RV forecast (the research consensus 50/50 cone input).
    Returns None only when every operand is missing."""
    vals, wts = [], []
    for i, s in enumerate(sigmas):
        if s is None or not math.isfinite(s):
            continue
        vals.append(float(s))
        wts.append(weights[i] if weights is not None else 1.0)
    if not vals:
        return None
    tot = sum(wts)
    return sum(v * w for v, w in zip(vals, wts)) / tot if tot > 0 else None


def cone_sigma(v_garch, o, h, l, c, ret):
    """The per-bar cone sigma recipe, in ONE place so analyze.py (live) and
    backfill.py (backtest) can never drift: blend the GARCH conditional sigma with
    a HAR-RV forecast over a Rogers-Satchell realized-variance series (50/50), and
    fall back to EWMA of the returns when neither is available. Callers pass the
    GARCH sigma they already fitted (it is expensive) so it is computed once.
    Returns (sigma_cone, v_har)."""
    hv = har_rv_forecast(rogers_satchell_var(o, h, l, c))
    v_har = hv ** 0.5 if hv and hv > 0 else None
    blended = blend_sigma(v_garch, v_har)
    return (blended if blended is not None else ewma_vol(ret)), v_har


# --------------------------------------------------------------------------- #
# RSI — Wilder formulation (matches TradingView)
# --------------------------------------------------------------------------- #
def rsi_wilder(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Wilder's RSI, the exact formulation TradingView uses. Returns an array
    aligned to `closes` with NaN for the warm-up region.
    """
    c = np.asarray(closes, dtype=float)
    delta = np.diff(c)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    rsi = np.full(c.size, np.nan)
    if delta.size < period:
        return rsi
    avg_gain = gain[:period].mean()
    avg_loss = loss[:period].mean()
    for i in range(period, delta.size + 1):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gain[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i - 1]) / period
        rs = np.inf if avg_loss == 0 else avg_gain / avg_loss
        rsi[i] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


# --------------------------------------------------------------------------- #
# Monte Carlo cones — three tail models. Gaussian understates tail risk on
# assets with fat tails (gold, crypto); bootstrap and Student-t expose it.
# --------------------------------------------------------------------------- #
_PCTS = (5, 25, 50, 75, 95)


def _summarize_paths(S0: float, terminal: np.ndarray) -> dict:
    pct = np.percentile(terminal, _PCTS)
    return {
        "S0": S0,
        "P5": float(pct[0]), "P25": float(pct[1]), "P50": float(pct[2]),
        "P75": float(pct[3]), "P95": float(pct[4]),
        "p_up": float(np.mean(terminal > S0)),
        # Named to be explicit: E[terminal] of a lognormal sits ABOVE the median
        # even at zero drift (Jensen), so it must NOT be read as an expected move.
        # Deliver the median (P50) and the band; this is kept for completeness.
        "mean_lognormal": float(np.mean(terminal)),
    }


def mc_gaussian(S0: float, sigma_bar: float, horizon: int,
                drift: float = 0.0, n: int = 20000, seed: int = 7) -> dict:
    """Zero-drift-by-default Gaussian cone. The honest, assumption-free baseline."""
    rng = np.random.default_rng(seed)
    shocks = rng.normal(drift, sigma_bar, size=(n, horizon))
    terminal = S0 * np.exp(shocks.sum(axis=1))
    out = _summarize_paths(S0, terminal)
    out["model"] = "gaussian"
    return out


def mc_bootstrap(S0: float, returns: np.ndarray, horizon: int,
                 drift_zero: bool = True, n: int = 20000, seed: int = 7) -> dict:
    """
    Resample ACTUAL historical log returns with replacement. Inherits the real
    fat tails and skew of the series — no distributional assumption. Centred to
    zero drift by default so the cone is pure volatility, not a bet.
    """
    rng = np.random.default_rng(seed)
    r = np.asarray(returns, dtype=float)
    if drift_zero:
        r = r - r.mean()
    draws = rng.choice(r, size=(n, horizon), replace=True)
    terminal = S0 * np.exp(draws.sum(axis=1))
    out = _summarize_paths(S0, terminal)
    out["model"] = "bootstrap"
    return out


def mc_block(S0: float, returns: np.ndarray, horizon: int,
             drift_zero: bool = True, n: int = 20000, seed: int = 7,
             expected_block: float = 5.0) -> dict:
    """
    Horizon cone from the STATIONARY BLOCK bootstrap: like mc_bootstrap but the
    resampled returns come in contiguous blocks, so the paths inherit serial
    dependence (momentum/mean-reversion). Wider than the i.i.d. cone under VR>1 —
    the regime the engine trades — so a stop/target read off THIS cone stays
    momentum-aware while both barriers share one distribution (consistent R:R).
    """
    r = np.asarray(returns, dtype=float)
    if r.size == 0 or horizon < 1:
        return {"S0": S0, "model": "block_bootstrap"}
    if drift_zero:
        r = r - r.mean()
    rng = np.random.default_rng(seed)
    idx = stationary_bootstrap_indices(r.size, horizon, expected_block, n, rng)
    terminal = S0 * np.exp(r[idx].sum(axis=1))
    out = _summarize_paths(S0, terminal)
    out["model"] = "block_bootstrap"
    return out


def mc_student_t(S0: float, returns: np.ndarray, horizon: int,
                 drift_zero: bool = True, n: int = 20000, seed: int = 7) -> dict:
    """
    Parametric fat-tail cone: fit a Student-t to the returns (df estimates tail
    heaviness) and simulate. Falls back to Gaussian if scipy is unavailable.
    """
    r = np.asarray(returns, dtype=float)
    if not _HAS_SCIPY:
        sig = close_to_close_vol(r)
        out = mc_gaussian(S0, sig, horizon, 0.0, n, seed)
        out["model"] = "student_t(fallback=gaussian)"
        return out
    df, loc, scale = stats.t.fit(r)
    # A Student-t with df<=2 has infinite variance (df<=1 infinite mean); on a
    # short noisy sample the MLE can land there, making the simulated cone blow
    # up. Fall back to the assumption-free bootstrap cone, whose draws are actual
    # observed returns and therefore bounded, and flag the degenerate fit.
    if not math.isfinite(df) or df <= 2.0 or not math.isfinite(scale) or scale <= 0:
        out = mc_bootstrap(S0, r, horizon, drift_zero, n, seed)
        out["model"] = f"bootstrap(fallback: student_t df={df:.2f} degenerate)"
        out["df"] = float(df)
        return out
    rng = np.random.default_rng(seed)
    draws = stats.t.rvs(df, loc=loc, scale=scale, size=(n, horizon),
                        random_state=rng)
    if drift_zero:
        draws = draws - draws.mean()
    terminal = S0 * np.exp(draws.sum(axis=1))
    out = _summarize_paths(S0, terminal)
    out["model"] = f"student_t(df={df:.1f})"
    out["df"] = float(df)
    return out


# --------------------------------------------------------------------------- #
# Conditional probabilities — with confidence, not just a raw rate
# --------------------------------------------------------------------------- #
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple:
    """
    Wilson score interval for a proportion. Far better than k/n +/- 1.96*SE at
    small n and near 0/1, which is exactly the regime that traps pattern stats.
    """
    if n == 0:
        return (0.0, 1.0)
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass
class Conditional:
    name: str
    n: int
    up: int
    rate: float
    ci95: tuple
    baseline: float
    edge: float          # rate - baseline
    p_value: float       # two-sided binomial test vs baseline
    verdict: str         # "edge" | "no-edge" | "thin-sample"
    p_adjusted: float = float("nan")   # family-corrected p (Benjamini-Hochberg)

    def as_dict(self):
        return asdict(self)


def conditional_next_up(name: str, mask: np.ndarray, next_up: np.ndarray,
                        baseline: float, min_n: int = 30) -> Conditional:
    """
    Given a boolean condition on bar t and whether bar t+1 closed up, measure
    the conditional P(next up) with a Wilson CI and a binomial test against the
    unconditional baseline. A condition is only an 'edge' when the sample is
    thick enough AND the CI clears the baseline — the guardrail that stops a
    12-sample bucket from masquerading as a signal.
    """
    m = np.asarray(mask, dtype=bool)
    u = np.asarray(next_up, dtype=bool)
    sel = u[m]
    n = int(sel.size)
    up = int(sel.sum())
    rate = up / n if n else 0.0
    ci = wilson_ci(up, n)
    if _HAS_SCIPY and n > 0:
        p_value = float(stats.binomtest(up, n, baseline).pvalue)
    else:
        p_value = float("nan")
    if n < min_n:
        verdict = "thin-sample"
    elif ci[0] > baseline or ci[1] < baseline:
        verdict = "edge"
    else:
        verdict = "no-edge"
    return Conditional(name, n, up, rate, ci, baseline, rate - baseline,
                       p_value, verdict)


def benjamini_hochberg(pvalues, alpha: float = 0.05):
    """
    Benjamini-Hochberg FDR procedure. Returns (reject, p_adjusted) as arrays
    aligned to the input. Controls the false-discovery rate across a family of
    simultaneous tests, which is exactly what a menu of conditional signals or a
    parameter sweep needs: testing k conditions each at alpha inflates the
    family-wise false-positive rate to ~1-(1-alpha)^k.
    """
    p = np.asarray(pvalues, dtype=float)
    m = p.size
    reject = np.zeros(m, dtype=bool)
    padj = np.ones(m)
    if m == 0:
        return reject, padj
    order = np.argsort(p)
    ps = p[order]
    ranks = np.arange(1, m + 1)
    # step-up rejection: largest k with p_(k) <= (k/m)*alpha rejects ranks 1..k
    below = np.nonzero(ps <= ranks / m * alpha)[0]
    rej_sorted = np.zeros(m, dtype=bool)
    if below.size:
        rej_sorted[: below.max() + 1] = True
    # monotone adjusted p-values, enforced from the largest rank down
    adj_sorted = np.clip(np.minimum.accumulate((ps * m / ranks)[::-1])[::-1], 0.0, 1.0)
    reject[order] = rej_sorted
    padj[order] = adj_sorted
    return reject, padj


def correct_conditionals(conditionals, alpha: float = 0.05):
    """
    Apply Benjamini-Hochberg across the FAMILY of conditional tests, in place.
    An individual Wilson CI clearing the baseline is not an edge once you count
    how many conditions were tried; this re-labels each verdict by FDR-controlled
    significance and records `p_adjusted`. Thin-sample / NaN-p conditions are
    excluded from the family and left untouched.
    """
    testable = [c for c in conditionals
                if c.verdict != "thin-sample" and c.p_value == c.p_value]
    if not testable:
        return conditionals
    reject, padj = benjamini_hochberg([c.p_value for c in testable], alpha)
    for c, rej, pa in zip(testable, reject, padj):
        c.p_adjusted = float(pa)
        c.verdict = "edge" if rej else "no-edge"
    return conditionals
