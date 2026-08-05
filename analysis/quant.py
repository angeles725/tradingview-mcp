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
def log_returns(closes: np.ndarray) -> np.ndarray:
    """Per-bar log returns r_t = ln(C_t / C_{t-1})."""
    c = np.asarray(closes, dtype=float)
    return np.diff(np.log(c))


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

    # Standard error of the slope and its 95% CI (t approx by 1.96 for n>>1).
    dof = max(n - 2, 1)
    sigma2 = ss_res / dof
    se_slope = math.sqrt(sigma2 / sxx) if sxx > 0 else float("inf")
    t_stat = slope / se_slope if se_slope > 0 else 0.0
    tcrit = stats.t.ppf(0.975, dof) if _HAS_SCIPY else 1.96
    half = tcrit * se_slope
    ci95 = (slope - half, slope + half)

    theil = theilsen_slope(y)
    significant = (ci95[0] > 0 or ci95[1] < 0) and r2 >= r2_floor
    return Trend(slope, r2, t_stat, ci95, theil, significant, n)


def theilsen_slope(y: np.ndarray) -> float:
    """Median of pairwise slopes — robust to outliers/spikes. O(n^2) but n<=300."""
    y = np.asarray(y, dtype=float)
    n = y.size
    i, j = np.triu_indices(n, k=1)
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
    """
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(n_boot, x.size))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


# --------------------------------------------------------------------------- #
# Volatility — several estimators, because close-to-close wastes OHLC and
# assumes constant variance. Report per-bar sigma; scale downstream.
# --------------------------------------------------------------------------- #
def close_to_close_vol(returns: np.ndarray) -> float:
    """Plain stdev of log returns (sample). Baseline, noisiest estimator."""
    r = np.asarray(returns, dtype=float)
    return float(np.std(r, ddof=1))


def ewma_vol(returns: np.ndarray, lam: float = 0.94) -> float:
    """
    RiskMetrics EWMA (an IGARCH). Weights recent bars more, so it tracks
    volatility CLUSTERING and returns the *current-conditional* sigma rather
    than a flat historical average. lam=0.94 is the RiskMetrics daily default.
    """
    r = np.asarray(returns, dtype=float)
    var = r[0] ** 2
    for x in r[1:]:
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


def garch11_vol(returns: np.ndarray):
    """
    Fit a GARCH(1,1) by Gaussian MLE and return the one-step-ahead conditional
    sigma. Captures volatility clustering with mean reversion (unlike EWMA,
    which never reverts). Returns (sigma, params) or None if scipy is absent or
    the optimiser fails; callers fall back to EWMA.
    """
    if not _HAS_SCIPY:
        return None
    r = np.asarray(returns, dtype=float)
    r = r - r.mean()
    var0 = np.var(r)
    if var0 <= 0:
        return None

    def nll(theta):
        omega, alpha, beta = theta
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.999:
            return 1e12
        sigma2 = np.empty_like(r)
        sigma2[0] = var0
        for t in range(1, r.size):
            sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]
        return 0.5 * np.sum(np.log(2 * np.pi * sigma2) + r ** 2 / sigma2)

    x0 = np.array([var0 * 0.05, 0.05, 0.90])
    try:
        res = optimize.minimize(
            nll, x0, method="Nelder-Mead",
            options={"maxiter": 4000, "xatol": 1e-10, "fatol": 1e-10},
        )
    except Exception:
        return None
    if not res.success and res.fun >= 1e11:
        return None
    omega, alpha, beta = res.x
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1:
        return None
    sigma2 = var0
    for t in range(1, r.size):
        sigma2 = omega + alpha * r[t - 1] ** 2 + beta * sigma2
    sigma_next = omega + alpha * r[-1] ** 2 + beta * sigma2
    return math.sqrt(sigma_next), {"omega": omega, "alpha": alpha, "beta": beta}


def scale_sigma(sigma_bar: float, horizon: int) -> float:
    """Random-walk scaling of per-bar sigma to an N-bar horizon."""
    return sigma_bar * math.sqrt(horizon)


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
        "mean": float(np.mean(terminal)),
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
