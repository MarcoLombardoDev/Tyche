# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
stats_tests.py — Tyche

The handful of distributions and tail probabilities the analysis needs,
implemented here rather than imported.

SciPy would supply all of it in one line each. It is not a dependency because
Tyche needs exactly four functions from it, SciPy is the single heaviest
addition available to a PyInstaller bundle, and — the reason that actually
decided it — every number in :mod:`core.validation` is a claim about whether
a prediction beat chance. A reader has to be able to check how that p-value
was produced without leaving the repository.

Accuracy is verified in ``tests/test_core.py`` against textbook values to
1e-10, which is nine more digits than any conclusion here rests on.
"""

from __future__ import annotations

import math

# Iteration caps for the incomplete-gamma routines. Both converge in well
# under a hundred steps across the range Tyche uses; the caps exist so a
# pathological input degrades to a slightly wrong answer instead of a hang.
_MAX_ITER = 300
_EPS = 1e-14
_FPMIN = 1e-300


def _gamma_series(a: float, x: float) -> float:
    """Lower regularised incomplete gamma P(a, x) by series. Good for x < a+1."""
    ap = a
    total = delta = 1.0 / a
    for _ in range(_MAX_ITER):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_cf(a: float, x: float) -> float:
    """Upper regularised incomplete gamma Q(a, x) by continued fraction.

    Lentz's algorithm. Good for x >= a+1, which is where the series above
    converges slowly enough to matter.
    """
    b = x + 1.0 - a
    c = 1.0 / _FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, _MAX_ITER):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi2_sf(x: float, df: int) -> float:
    """P(X > x) for a chi-square with ``df`` degrees of freedom.

    Returns 1.0 for x <= 0 rather than raising: a chi-square statistic of
    exactly zero is a perfect fit, whose p-value is 1, and callers should not
    have to special-case the degenerate sample that produces it.
    """
    if df <= 0:
        raise ValueError("degrees of freedom must be positive")
    if x <= 0:
        return 1.0
    a, half = df / 2.0, x / 2.0
    if half < a + 1.0:
        return 1.0 - _gamma_series(a, half)
    return _gamma_cf(a, half)


def normal_sf(z: float) -> float:
    """P(Z > z) for a standard normal."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def two_sided_normal_p(z: float) -> float:
    """Two-sided p-value for a z statistic."""
    return min(1.0, 2.0 * normal_sf(abs(z)))


def hypergeom_pmf(population: int, successes: int, draws: int, k: int) -> float:
    """P(exactly k successes) drawing ``draws`` items without replacement.

    This is the null distribution of a SuperEnalotto prediction: pick six
    numbers out of ninety, six are drawn, and the number you got right is
    hypergeometric with population 90, six successes in the population and six
    draws. Its mean is 6·6/90 = 0.4 — the number every forecast in Tyche is
    measured against.
    """
    if k < 0 or k > draws or k > successes:
        return 0.0
    if draws - k > population - successes:
        return 0.0
    return math.exp(
        _log_comb(successes, k)
        + _log_comb(population - successes, draws - k)
        - _log_comb(population, draws)
    )


def _log_comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def hypergeom_moments(population: int, successes: int, draws: int) -> tuple[float, float]:
    """``(mean, variance)`` of the hypergeometric above.

    The variance carries the finite-population correction, which is not a
    rounding detail here: without it the standard error of a 3,000-draw
    backtest comes out about 3% too wide, and a marginal result would be
    reported as less significant than it is.
    """
    n, k_, d = population, successes, draws
    mean = d * k_ / n
    if n <= 1:
        return mean, 0.0
    variance = d * (k_ / n) * ((n - k_) / n) * ((n - d) / (n - 1))
    return mean, variance


def chi_square_goodness_of_fit(
    observed: list[float], expected: list[float]
) -> tuple[float, int, float]:
    """``(statistic, dof, p_value)`` for a one-way goodness-of-fit test.

    Bins whose expected count is below 5 are pooled into their neighbour on
    the right, and the last one leftwards, because Pearson's approximation
    stops being trustworthy there. That is why ``dof`` is returned rather than
    assumed by the caller: pooling changes it, and a p-value read against the
    wrong number of bins is worse than no p-value.
    """
    if len(observed) != len(expected):
        raise ValueError("observed and expected must be the same length")
    obs, exp = list(observed), list(expected)

    i = 0
    while i < len(exp) - 1:
        if exp[i] < 5:
            exp[i + 1] += exp[i]
            obs[i + 1] += obs[i]
            del exp[i], obs[i]
        else:
            i += 1
    while len(exp) > 1 and exp[-1] < 5:
        exp[-2] += exp[-1]
        obs[-2] += obs[-1]
        del exp[-1], obs[-1]

    if len(exp) < 2:
        return 0.0, 0, 1.0
    statistic = sum((o - e) ** 2 / e for o, e in zip(obs, exp, strict=True) if e > 0)
    dof = len(exp) - 1
    return statistic, dof, chi2_sf(statistic, dof)
