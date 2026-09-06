# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
scoring.py — Tyche

Rank-based scoring of a forecast against the draw that followed it.

Why this module exists
----------------------

The walk-forward harness scored one thing: how many of a method's top six
numbers came out. That statistic **throws away 84 of the 90 numbers a method
ranked**. A number placed 7th and a number placed 90th contribute the same
zero, so any edge that reorders the field without pushing numbers into the top
six is invisible to it.

That matters because the hit count is a blunt instrument. Its null is
hypergeometric with mean 0.4 and variance 0.3524 — a standard deviation half
again the mean — so a 1,000-draw run has a standard error of about 19 hits
against an expected 400. An edge has to be large to clear that.

A rank statistic uses every draw's whole ranking. It is the same experiment
read with a finer gauge, and :mod:`core.power` measures how much finer.

Why rank metrics and not log loss or Brier
------------------------------------------

Proper scoring rules are the textbook answer and they do not apply here. Log
loss and the Brier score need *calibrated probabilities*, and none of Tyche's
methods produce any: ``frequenza`` returns a rate, ``ritardo`` a count of
draws, TimesFM an arbitrary real. Turning those into probabilities needs a
link function with a free temperature, and that temperature would decide the
comparison — fit it on the test draws and the result is leakage, fix it by
hand and the number measures the choice rather than the method.

Rank metrics are invariant under every monotone transform of the score, so
there is nothing to choose and nothing to leak. They answer the question the
program actually asks, which is whether a method orders the ninety numbers
better than an arbitrary order does.

Ties are not a detail
---------------------

``frequenza`` scores 90 numbers on 14 distinct values, with tie groups as
large as 17. :func:`core.predictor.rank_numbers` breaks those ties by the
number itself, so number 3 outranks number 80 whenever they are level. For a
top-six count that is an arbitrary but harmless convention. For a rank
statistic it is fatal: the metric would read the tie-break as a signal, and a
method that scores every number identically would appear to favour low
numbers.

So this module ranks with **mid-ranks** — every member of a tie group gets the
group's average rank. There is a test for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.archive import NUMBER_MAX, NUMBERS_PER_DRAW

# The mean of the mid-ranks over all ninety numbers, which is 45.5 whatever
# the ties are: mid-ranking redistributes ranks inside a group without
# changing their sum. That makes it the null mean of a drawn number's rank,
# with no assumption about the score distribution.
MEAN_RANK = (NUMBER_MAX + 1) / 2


def mid_ranks(scores: dict[int, float]) -> dict[int, float]:
    """Rank the numbers best-first, giving tied numbers the group's mean rank.

    Rank 1 is the highest score. A three-way tie for 4th, 5th and 6th place
    puts all three at 5.0.
    """
    order = sorted(scores, key=lambda n: -scores[n])
    ranks: dict[int, float] = {}
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1  # positions i..j, one-based, averaged
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def rank_null_variance(ranks: dict[int, float], picks: int = NUMBERS_PER_DRAW) -> float:
    """Variance of the mean rank of ``picks`` numbers drawn uniformly at random.

    Computed from the rank multiset actually produced rather than from the
    untied formula, because ties shrink it: a method that scores every number
    the same has every rank equal to 45.5 and a null variance of zero, which
    is correct — such a method cannot deviate from chance and must never be
    credited with having failed to.

    Sampling without replacement, so the finite-population correction applies.
    """
    n = len(ranks)
    if n <= 1 or picks <= 0:
        return 0.0
    values = list(ranks.values())
    mean = sum(values) / n
    population_variance = sum((v - mean) ** 2 for v in values) / n
    return (population_variance / picks) * (n - picks) / (n - 1)


@dataclass(frozen=True)
class DrawScore:
    """One method's ranking judged against one draw."""

    mean_rank: float
    null_variance: float
    top_hits: dict[int, int]


def score_draw(
    scores: dict[int, float],
    actual: set[int],
    tops: tuple[int, ...] = (NUMBERS_PER_DRAW, 10, 20),
) -> DrawScore:
    """Judge a full 90-number ranking against the six numbers that came out.

    ``mean_rank`` below 45.5 means the drawn numbers sat higher in the ranking
    than an arbitrary order would have put them. ``top_hits`` counts how many
    of them fell in the best *k* for each *k* asked for — the top-six entry is
    the statistic the harness has always reported.
    """
    ranks = mid_ranks(scores)
    drawn = sorted(actual)
    mean_rank = sum(ranks[n] for n in drawn) / len(drawn)

    # Ranking by score and taking the first k is the same operation the
    # predictor performs, tie-break included, so top_hits stays comparable
    # with the hit counts the harness reported before this module existed.
    order = sorted(scores, key=lambda n: (-scores[n], n))
    top_hits = {k: len(actual & set(order[:k])) for k in tops}

    return DrawScore(
        mean_rank=mean_rank,
        null_variance=rank_null_variance(ranks, len(drawn)),
        top_hits=top_hits,
    )
