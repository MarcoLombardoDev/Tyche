# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
statistics.py — Tyche

Table-ready descriptive statistics, so the GUI panels contain layout and
nothing else.

Every function here reports a deviation *and* the deviation chance produces,
in the same row. A frequency table that says "85 came up 239 times, 60 came up
170" is the raw material of every lottery system ever sold; the same table
with "expected 205 ± 14" beside it says the same thing and means the opposite.
Putting the two apart — numbers in the panel, caveat in a paragraph
underneath — is how the caveat stops being read.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.archive import ALL_NUMBERS, NUMBER_MAX, NUMBERS_PER_DRAW, Draw
from core.features import counts, current_gaps, decade_profile, pair_counts


@dataclass(frozen=True)
class NumberStat:
    """One row of the frequency table."""

    number: int
    count: int
    expected: float
    sigma: float          # deviation from expectation, in standard deviations
    gap: int              # draws since it last appeared
    expected_gap: float
    last_seen: str

    @property
    def unusual(self) -> bool:
        """Beyond two standard deviations — flagged, not meaningful.

        Across ninety numbers about four rows will exceed 2σ every time, by
        construction. The flag marks the extremes of a normal spread so the
        panel can show that they exist and are unremarkable; a user who sees
        four flags out of ninety has been told more than one who sees none.
        """
        return abs(self.sigma) >= 2.0


def number_table(draws: list[Draw]) -> list[NumberStat]:
    """The ninety numbers with their counts, gaps, and expected values."""
    total = len(draws)
    tally = counts(draws)
    gaps = current_gaps(draws)
    expected = total * NUMBERS_PER_DRAW / NUMBER_MAX
    p = NUMBERS_PER_DRAW / NUMBER_MAX
    sigma_count = math.sqrt(total * p * (1 - p)) if total else 0.0
    expected_gap = (1 - p) / p
    last_index: dict[int, int] = {}
    for i, draw in enumerate(draws):
        for n in draw.numbers:
            last_index[n] = i
    rows = []
    for n in ALL_NUMBERS:
        i = last_index.get(n)
        rows.append(NumberStat(
            number=n,
            count=tally[n],
            expected=expected,
            sigma=(tally[n] - expected) / sigma_count if sigma_count else 0.0,
            gap=gaps[n],
            expected_gap=expected_gap,
            last_seen=draws[i].date.isoformat() if i is not None else "never",
        ))
    return rows


def decade_table(draws: list[Draw]) -> list[tuple[str, int, float, float]]:
    """``(label, observed, expected, ratio)`` per ten-number band.

    Nine bands of exactly ten numbers, so each expects the same share and the
    ratio column is directly comparable across rows. The expected column is
    returned anyway rather than left to the panel, because the version of this
    table that ships on lottery sites shows the counts alone.
    """
    totals = [0] * 9
    for draw in draws:
        for i, c in enumerate(decade_profile(draw)):
            totals[i] += c
    drawn = len(draws) * NUMBERS_PER_DRAW
    sizes = [10] * 9
    rows = []
    for i, (observed, size) in enumerate(zip(totals, sizes, strict=True)):
        low = i * 10 + 1
        high = min(low + size - 1, NUMBER_MAX)
        expected = drawn * size / NUMBER_MAX if drawn else 0.0
        rows.append((f"{low}–{high}", observed, expected, observed / expected if expected else 0.0))
    return rows


def top_pairs(draws: list[Draw], limit: int = 20) -> list[tuple[int, int, int, float]]:
    """``(a, b, observed, expected)`` for the most frequent pairs.

    There are C(90,2) = 4,005 pairs and a few thousand draws contributing
    fifteen pairs each, so the expected count per pair is around twelve and the
    top of this table is almost pure noise — the maximum of 4,005 roughly
    Poisson counts sits four or five standard deviations above the mean *by
    definition*. The expected column is in the return value so the panel
    cannot show the ranking without it.
    """
    tally = pair_counts(draws)
    per_draw_pairs = math.comb(NUMBERS_PER_DRAW, 2)
    total_pairs = math.comb(NUMBER_MAX, 2)
    expected = len(draws) * per_draw_pairs / total_pairs if draws else 0.0
    ordered = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [(a, b, c, expected) for (a, b), c in ordered]


def summary_lines(draws: list[Draw]) -> list[str]:
    """A few sentences for the top of the statistics panel."""
    if not draws:
        return ["The archive is empty. Update it from the Archive tab."]
    total = len(draws)
    tally = counts(draws)
    expected = total * NUMBERS_PER_DRAW / NUMBER_MAX
    p = NUMBERS_PER_DRAW / NUMBER_MAX
    sigma = math.sqrt(total * p * (1 - p))
    hottest = max(tally, key=lambda n: tally[n])
    coldest = min(tally, key=lambda n: tally[n])
    spread = tally[hottest] - tally[coldest]
    gaps = current_gaps(draws)
    longest = max(gaps, key=lambda n: gaps[n])
    return [
        f"{total:,} draws from {draws[0].date} to {draws[-1].date}.",
        f"Each number is expected {expected:.0f} times, give or take {sigma:.0f}.",
        f"Most drawn: {hottest} ({tally[hottest]}). Least drawn: {coldest} ({tally[coldest]}). "
        f"Spread {spread}, which for ninety numbers with a {sigma:.0f} standard deviation "
        f"is about what randomness produces.",
        f"Longest current absence: {longest}, {gaps[longest]} draws. Its chance of coming "
        f"up next is {p:.4f} — the same as every other number's.",
    ]
