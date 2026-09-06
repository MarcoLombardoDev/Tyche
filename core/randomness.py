# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

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
from core.localise import it_number
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
        return TestResult("Uniformità dei 90 numeri", 0.0, 0, 1.0, "Estrazioni insufficienti.")
    statistic = sum((tally[n] - expected) ** 2 / expected for n in tally)
    dof = NUMBER_MAX - 1
    p = chi2_sf(statistic, dof)
    hottest = max(tally, key=lambda n: tally[n])
    coldest = min(tally, key=lambda n: tally[n])
    return TestResult(
        name="Uniformità dei 90 numeri",
        statistic=statistic,
        dof=dof,
        p_value=p,
        verdict=_verdict(
            p,
            "che alcuni numeri escano davvero più spesso",
            "che ogni numero esca con la stessa frequenza",
        ),
        detail=(
            f"attese {expected:.1f} uscite per numero; il più estratto è {hottest} "
            f"({tally[hottest]}), il meno estratto {coldest} ({tally[coldest]})"
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
        return TestResult("Distribuzione dei ritardi", 0.0, 0, 1.0, "Estrazioni insufficienti.")

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
        name="Distribuzione dei ritardi",
        statistic=statistic,
        dof=dof,
        p_value=p,
        verdict=_verdict(
            p,
            "che i ritardi non seguano la legge delle estrazioni indipendenti",
            "che i ritardi siano esattamente quelli di estrazioni indipendenti",
        ),
        detail=(
            f"{it_number(total)} ritardi osservati, media {mean_gap:.2f}, "
            f"attesa geometrica {(1 - p_hit) / p_hit:.2f}"
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
        return TestResult(
            "Indipendenza seriale (estrazione t → t+1)", 0.0, 0, 1.0,
            "Estrazioni insufficienti.",
        )
    now, nxt = presence[:, :-1], presence[:, 1:]
    a = float(((now > 0) & (nxt > 0)).sum())   # drawn, then drawn
    b = float(((now > 0) & (nxt == 0)).sum())  # drawn, then not
    c = float(((now == 0) & (nxt > 0)).sum())  # not, then drawn
    d = float(((now == 0) & (nxt == 0)).sum())
    n = a + b + c + d
    row1, row2, col1, col2 = a + b, c + d, a + c, b + d
    if min(row1, row2, col1, col2) == 0:
        return TestResult(
            "Indipendenza seriale (estrazione t → t+1)", 0.0, 0, 1.0,
            "Tabella degenere.",
        )
    statistic = n * (a * d - b * c) ** 2 / (row1 * row2 * col1 * col2)
    p = chi2_sf(statistic, 1)
    rate_after_hit = a / row1
    rate_after_miss = c / row2
    return TestResult(
        name="Indipendenza seriale (estrazione t → t+1)",
        statistic=statistic,
        dof=1,
        p_value=p,
        verdict=_verdict(
            p,
            "che l'estrazione precedente dica qualcosa sulla successiva",
            "che l'estrazione precedente non dica nulla sulla successiva",
        ),
        detail=(
            f"P(esce | uscito la volta scorsa) = {rate_after_hit:.4f}, "
            f"P(esce | non uscito la volta scorsa) = {rate_after_miss:.4f}, "
            f"non condizionata {NUMBERS_PER_DRAW / NUMBER_MAX:.4f}"
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
        return TestResult(
            "Ripetizioni fra estrazioni consecutive", 0.0, 0, 1.0,
            "Estrazioni insufficienti.",
        )
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
        name="Ripetizioni fra estrazioni consecutive",
        statistic=statistic,
        dof=dof,
        p_value=p,
        verdict=_verdict(
            p,
            "che le ripetizioni non seguano la distribuzione del caso",
            "che le ripetizioni siano esattamente quelle previste dal caso",
        ),
        detail=f"sovrapposizione media {mean_overlap:.3f} su 6, attesa dal caso 0.400",
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
        return TestResult("Somma dei sei numeri", 0.0, 0, 1.0, "Estrazioni insufficienti.")
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
        name="Somma dei sei numeri",
        statistic=z,
        dof=0,
        p_value=p,
        verdict=_verdict(
            p,
            "che l'estrazione sia sbilanciata verso numeri alti o bassi",
            "che l'estrazione non mostri sbilanciamenti verso alto o basso",
        ),
        detail=(
            f"media osservata {mean_obs:.2f}, attesa {mean_null:.2f} "
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


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the order given.

    Five tests at the 5% level flag something by chance 23% of the time, so a
    single flag among five is not the 5% event the number beside it suggests.
    The old wording said so in prose — "about one test in twenty does this by
    chance" — which leaves the reader to do the correction in their head and
    gives them nothing to do it with.

    Holm rather than plain Bonferroni because it is uniformly more powerful
    and just as safe: it controls the same family-wise error rate without
    multiplying every p-value by the number of tests. Sorted ascending, the
    *i*-th smallest is scaled by ``n - i`` rather than by ``n``, then the
    sequence is made non-decreasing so a small p-value cannot end up adjusted
    below a smaller one.

    Not FDR: with five tests the question is "is any of these real", which is
    the family-wise question, and Benjamini-Hochberg answers a different one
    that only starts to pay off with far more tests than this.
    """
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    adjusted = [0.0] * n
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (n - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def summarise(results: list[TestResult]) -> str:
    """One paragraph the user can read instead of five p-values."""
    adjusted = holm_adjust([r.p_value for r in results])
    flagged = [r for r in results if r.significant]
    survivors = [r for r, a in zip(results, adjusted, strict=True) if a < ALPHA]

    if not flagged:
        return (
            f"Tutti e {len(results)} i test sono compatibili con estrazioni indipendenti "
            "e uniformi. Su questa evidenza l'archivio non contiene struttura "
            "sfruttabile, e nessuna previsione costruita su di esso — compresa quella "
            "di TimesFM — può fare meglio del caso."
        )

    names = ", ".join(r.name for r in flagged)
    verb = "si discosta" if len(flagged) == 1 else "si discostano"
    # With five tests the probability that at least one clears 5% by chance
    # alone is 1 - 0.95^5, which is where the reader has to start.
    by_chance = 1 - (1 - ALPHA) ** len(results)
    head = (
        f"{len(flagged)} test su {len(results)} {verb} dal modello di indipendenza "
        f"({names}). Con {len(results)} test la probabilità che almeno uno scenda "
        f"sotto il {ALPHA:.0%} per puro caso è del {by_chance:.0%}"
    )

    if not survivors:
        return (
            f"{head}, e infatti nessuno resta significativo dopo la correzione di "
            "Holm-Bonferroni per test multipli. Su questa evidenza non c'è niente "
            "da spiegare."
        )

    surviving = ", ".join(
        f"{r.name} (p corretto {a:.4f})"
        for r, a in zip(results, adjusted, strict=True)
        if a < ALPHA
    )
    plural = "resta" if len(survivors) == 1 else "restano"
    return (
        f"{head}. Dopo la correzione di Holm-Bonferroni per test multipli "
        f"{plural} {surviving}. Verifica comunque se il risultato si ripete su una "
        "porzione diversa dell'archivio prima di trarne qualcosa: una correzione "
        "governa la fortuna, non un archivio che sbaglia."
    )


def _verdict(p: float, if_small: str, if_large: str) -> str:
    # Both frames take the same clause, so the clause carries its own "che"
    # and stays in the subjunctive: "evidenza che … escano" and "l'ipotesi
    # che … escano" are both correct, while an indicative would be wrong after
    # the second.
    if p < ALPHA:
        return f"p = {p:.4f} — evidenza {if_small}."
    return f"p = {p:.4f} — nessuna evidenza contro l'ipotesi {if_large}."
