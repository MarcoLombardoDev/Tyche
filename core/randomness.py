# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
randomness.py — Tyche

Tests the archive against the hypothesis that it is exactly what it claims to
be: independent uniform draws of six numbers from ninety.

This module exists before the forecaster, and should be read before it. Every
prediction Tyche can make is worth something only if these tests fail, and
they do not fail. They are not a disclaimer bolted onto the side of the
product — they are the measurement that tells the user what the rest of the
product is doing.

Five tests, chosen because each one catches a different way the null could be
wrong, and between them they cover everything a player's intuition suspects:

- :func:`uniformity_test` — are some numbers drawn more often? (the "hot
  numbers" claim)
- :func:`gap_distribution_test` — does a number become due after a long
  absence? (*ritardo*, the most widely sold idea in Italian lottery play)
- :func:`serial_independence_test` — does what came out last time change what
  comes out next?
- :func:`repeat_count_test` — do numbers repeat from one draw to the next more
  or less often than chance?
- :func:`sum_distribution_test` — is the total of the six numbers distributed
  as it should be? (a joint test: it catches biases the per-number tests miss)

Each returns a :class:`TestResult` with a statistic, a p-value and a plain
sentence. A small p-value here would be genuinely interesting: it would mean
the draw machinery is biased. It has never been small on this archive, and
the correct reading of that is *the game is fair*, not *the test is too weak*.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.archive import NUMBER_MAX, NUMBERS_PER_DRAW, Draw
from core.features import counts, presence_matrix
from core.stats_tests import (
    chi2_sf,
    chi_square_goodness_of_fit,
    hypergeom_pmf,
    two_sided_normal_p,
)

# The conventional threshold, stated once. Nothing here treats it as a
# decision rule — a p-value is reported, and the verdict text says what the
# number means rather than converting it into a yes or a no.
ALPHA = 0.05


@dataclass(frozen=True)
class TestResult:
    """One hypothesis test, in a form the GUI can print without interpreting."""

    name: str
    statistic: float
    dof: int
    p_value: float
    verdict: str
    detail: str = ""

    @property
    def significant(self) -> bool:
        return self.p_value < ALPHA


def uniformity_test(draws: list[Draw]) -> TestResult:
    """Are all ninety numbers drawn equally often?

    Pearson chi-square on the 90 counts, 89 degrees of freedom. Under the null
    each number has probability 6/90 per draw, so the expected count is
    ``6·D/90`` for every one of them.

    The counts always *look* uneven — over 3,000 draws the gap between the
    most and least frequent number is typically 60 or 70 appearances, which is
    what sells frequency tables. The test is the check that the spread is the
    one randomness produces: the standard deviation of a count is about 14, so
    a 70-wide range across ninety numbers is unremarkable.
    """
    tally = counts(draws)
    total = len(draws)
    expected = total * NUMBERS_PER_DRAW / NUMBER_MAX
    if total == 0 or expected <= 0:
        return TestResult("Uniformity of the 90 numbers", 0.0, 0, 1.0, "Not enough draws.")
    statistic = sum((tally[n] - expected) ** 2 / expected for n in tally)
    dof = NUMBER_MAX - 1
    p = chi2_sf(statistic, dof)
    hottest = max(tally, key=lambda n: tally[n])
    coldest = min(tally, key=lambda n: tally[n])
    return TestResult(
        name="Uniformity of the 90 numbers",
        statistic=statistic,
        dof=dof,
        p_value=p,
        verdict=_verdict(
            p,
            "some numbers really are drawn more often",
            "every number is drawn equally often",
        ),
        detail=(
            f"expected {expected:.1f} appearances each; most drawn {hottest} "
            f"({tally[hottest]}), least drawn {coldest} ({tally[coldest]})"
        ),
    )


def gap_distribution_test(draws: list[Draw]) -> TestResult:
    """Do gaps between appearances follow the geometric law of independence?

    If draws are independent, the number of draws a given number waits between
    appearances is geometric with p = 6/90: P(gap = g) = p(1-p)^g. A number
    that became "due" after a long absence would show up as too few long gaps;
    a number with momentum, as too many.

    This is the test that matters most to an Italian player, because *ritardo*
    tables are the core of the folklore. The observed gap histogram matches
    the geometric one closely enough that the difference is not measurable —
    which is precisely why a 100-draw absence tells you nothing about the
    101st.
    """
    presence = presence_matrix(draws)
    p_hit = NUMBERS_PER_DRAW / NUMBER_MAX
    observed_gaps: list[int] = []
    for row in presence:
        hits = [t for t, v in enumerate(row) if v > 0]
        observed_gaps.extend(b - a - 1 for a, b in zip(hits, hits[1:], strict=False))
    if len(observed_gaps) < 100:
        return TestResult("Gap ('ritardo') distribution", 0.0, 0, 1.0, "Not enough draws.")

    # Bucket to 0..49 with a 50+ tail; beyond that the expected counts are
    # tiny and the pooling in the chi-square would merge them anyway.
    n_bins = 50
    observed = [0.0] * (n_bins + 1)
    for g in observed_gaps:
        observed[min(g, n_bins)] += 1
    total = len(observed_gaps)
    expected = [total * p_hit * (1 - p_hit) ** g for g in range(n_bins)]
    expected.append(total * (1 - p_hit) ** n_bins)

    statistic, dof, p = chi_square_goodness_of_fit(observed, expected)
    mean_gap = sum(observed_gaps) / total
    return TestResult(
        name="Gap ('ritardo') distribution",
        statistic=statistic,
        dof=dof,
        p_value=p,
        verdict=_verdict(
            p,
            "gaps do not follow the independent-draw law",
            "gaps are exactly those of independent draws",
        ),
        detail=(
            f"{total:,} gaps observed, mean {mean_gap:.2f}, "
            f"geometric expectation {(1 - p_hit) / p_hit:.2f}"
        ),
    )


def serial_independence_test(draws: list[Draw]) -> TestResult:
    """Does a number's appearance change its chance of appearing next time?

    A 2×2 contingency table pooled over all ninety numbers and all consecutive
    pairs of draws: drawn at *t* or not, against drawn at *t+1* or not. One
    degree of freedom.

    Pooling across numbers is what gives this test its power. Per number there
    are only a few thousand transitions and an effect would have to be huge to
    register; pooled there are 90 × (D−1), which is enough to detect a shift
    of well under a percentage point in the conditional rate.
    """
    presence = presence_matrix(draws)
    if presence.shape[1] < 3:
        return TestResult("Serial independence (draw t → t+1)", 0.0, 0, 1.0, "Not enough draws.")
    now, nxt = presence[:, :-1], presence[:, 1:]
    a = float(((now > 0) & (nxt > 0)).sum())   # drawn, then drawn
    b = float(((now > 0) & (nxt == 0)).sum())  # drawn, then not
    c = float(((now == 0) & (nxt > 0)).sum())  # not, then drawn
    d = float(((now == 0) & (nxt == 0)).sum())
    n = a + b + c + d
    row1, row2, col1, col2 = a + b, c + d, a + c, b + d
    if min(row1, row2, col1, col2) == 0:
        return TestResult("Serial independence (draw t → t+1)", 0.0, 0, 1.0, "Degenerate table.")
    statistic = n * (a * d - b * c) ** 2 / (row1 * row2 * col1 * col2)
    p = chi2_sf(statistic, 1)
    rate_after_hit = a / row1
    rate_after_miss = c / row2
    return TestResult(
        name="Serial independence (draw t → t+1)",
        statistic=statistic,
        dof=1,
        p_value=p,
        verdict=_verdict(
            p,
            "the previous draw carries information about the next",
            "the previous draw carries no information about the next",
        ),
        detail=(
            f"P(drawn | drawn last time) = {rate_after_hit:.4f}, "
            f"P(drawn | not drawn last time) = {rate_after_miss:.4f}, "
            f"unconditional {NUMBERS_PER_DRAW / NUMBER_MAX:.4f}"
        ),
    )


def repeat_count_test(draws: list[Draw]) -> TestResult:
    """How many numbers carry over from one draw to the next?

    Under independence the overlap between consecutive draws is
    hypergeometric(90, 6, 6) — the same distribution a prediction is scored
    against, which makes this test a direct sanity check on the yardstick used
    everywhere else in Tyche. Mean overlap 0.4; two or more repeats happen in
    about one draw in twenty.
    """
    if len(draws) < 2:
        return TestResult("Repeats between consecutive draws", 0.0, 0, 1.0, "Not enough draws.")
    overlaps = [
        len(set(a.numbers) & set(b.numbers))
        for a, b in zip(draws, draws[1:], strict=False)
    ]
    pairs = len(overlaps)
    observed = [float(overlaps.count(k)) for k in range(NUMBERS_PER_DRAW + 1)]
    expected = [pairs * hypergeom_pmf(NUMBER_MAX, NUMBERS_PER_DRAW, NUMBERS_PER_DRAW, k)
                for k in range(NUMBERS_PER_DRAW + 1)]
    statistic, dof, p = chi_square_goodness_of_fit(observed, expected)
    mean_overlap = sum(overlaps) / pairs
    return TestResult(
        name="Repeats between consecutive draws",
        statistic=statistic,
        dof=dof,
        p_value=p,
        verdict=_verdict(
            p,
            "repeats are not distributed as chance predicts",
            "repeats occur exactly as often as chance predicts",
        ),
        detail=f"mean overlap {mean_overlap:.3f} of 6, chance expectation 0.400",
    )


def sum_distribution_test(draws: list[Draw]) -> TestResult:
    """Is the sum of the six numbers distributed as independent sampling implies?

    A joint test rather than a per-number one. The sum has mean 6·(91/2) = 273
    and, sampling six without replacement from 1–90, standard deviation
    ``sqrt(6 · (90²−1)/12 · 84/89)`` ≈ 61.6. A z-test on the observed mean
    catches any bias that pushes the draw towards high or low numbers as a
    group — the kind of physical asymmetry (a heavier ball, a badly mixed
    drum) that leaves each individual number's count looking innocent.
    """
    if len(draws) < 30:
        return TestResult("Sum of the six numbers", 0.0, 0, 1.0, "Not enough draws.")
    sums = [sum(d.numbers) for d in draws]
    n = len(sums)
    mean_obs = sum(sums) / n
    mean_null = NUMBERS_PER_DRAW * (NUMBER_MAX + 1) / 2
    var_one = (NUMBER_MAX ** 2 - 1) / 12
    # Finite-population correction for drawing 6 of 90 without replacement.
    var_null = NUMBERS_PER_DRAW * var_one * (NUMBER_MAX - NUMBERS_PER_DRAW) / (NUMBER_MAX - 1)
    z = (mean_obs - mean_null) / ((var_null / n) ** 0.5)
    p = two_sided_normal_p(z)
    return TestResult(
        name="Sum of the six numbers",
        statistic=z,
        dof=0,
        p_value=p,
        verdict=_verdict(
            p,
            "the draw is biased towards high or low numbers",
            "the draw shows no high/low bias",
        ),
        detail=(
            f"observed mean {mean_obs:.2f}, expected {mean_null:.2f} "
            f"± {(var_null / n) ** 0.5:.2f}"
        ),
    )


def run_all(draws: list[Draw]) -> list[TestResult]:
    """Every test, in the order the GUI shows them."""
    return [
        uniformity_test(draws),
        gap_distribution_test(draws),
        serial_independence_test(draws),
        repeat_count_test(draws),
        sum_distribution_test(draws),
    ]


def summarise(results: list[TestResult]) -> str:
    """One paragraph the user can read instead of five p-values."""
    flagged = [r for r in results if r.significant]
    if not flagged:
        return (
            f"All {len(results)} tests are consistent with independent uniform draws. "
            "On this evidence the archive contains no exploitable structure, and no "
            "forecast built from it — TimesFM's included — can do better than chance."
        )
    names = ", ".join(r.name for r in flagged)
    return (
        f"{len(flagged)} of {len(results)} tests departed from the independence model "
        f"({names}). At the 5% level roughly one test in twenty does this by chance, so "
        "check whether the result repeats on a different slice of the archive before "
        "reading anything into it."
    )


def _verdict(p: float, if_small: str, if_large: str) -> str:
    if p < ALPHA:
        return f"p = {p:.4f} — evidence that {if_small}."
    return f"p = {p:.4f} — no evidence against the hypothesis that {if_large}."
