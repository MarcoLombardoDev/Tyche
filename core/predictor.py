# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
predictor.py — Tyche

Turns a score per number into numbers to play, and says what that is worth.

Four methods, and the point of having four is that they can be compared:

- ``timesfm``    — the 330M foundation model of :mod:`core.forecaster`.
- ``frequency``  — play the numbers drawn most often lately ("hot").
- ``gap``        — play the numbers absent longest ("ritardo", the Italian
  player's method, and the one every archive site's front page sells).
- ``random``     — six numbers from a seeded generator.

:mod:`core.validation` scores all four against the same draws. They come out
the same, because the thing they are ranking has no order. Keeping the naive
baselines in the product rather than in a footnote is what makes that
visible: a user who sees TimesFM tie with ``random`` has learned something a
paragraph of warning text cannot teach.

The odds functions are exact combinatorics, not estimates, and they are the
part of this module with unconditional value.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from core.archive import ALL_NUMBERS, NUMBER_MAX, NUMBERS_PER_DRAW, Draw
from core.features import DEFAULT_WINDOW, counts, current_gaps

METHODS = ("timesfm", "frequency", "gap", "random")


@dataclass(frozen=True)
class Prediction:
    """A set of combinations, the scores behind them, and their provenance."""

    method: str
    scores: dict[int, float]
    ranked: list[int]
    combinations: list[tuple[int, ...]]
    generated_at: datetime
    archive_last_date: date | None
    archive_size: int
    note: str = ""
    detail: dict = field(default_factory=dict)

    def to_log_entry(self) -> dict:
        return {
            "method": self.method,
            "generated_at": self.generated_at.isoformat(),
            "archive_last_date": (
                self.archive_last_date.isoformat() if self.archive_last_date else None
            ),
            "archive_size": self.archive_size,
            "combinations": [list(c) for c in self.combinations],
            "top_scores": {str(n): round(self.scores[n], 6) for n in self.ranked[:12]},
        }


# ─────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────

def frequency_scores(draws: list[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """How often each number came up in the last ``window`` draws.

    The "hot numbers" method. Over a window of 150 draws each number is
    expected 10 times with a standard deviation of about 3, so the hottest
    number in any given window is typically 6 or 7 ahead of the coldest by
    chance alone — which is exactly as much of a pattern as this produces.
    """
    recent = draws[-window:] if window else draws
    tally = counts(recent)
    total = max(len(recent), 1)
    return {n: tally[n] / total for n in ALL_NUMBERS}


def gap_scores(draws: list[Draw]) -> dict[int, float]:
    """Draws since each number last appeared — the *ritardo* method.

    Ranking by this plays the numbers that are "due". They are not due:
    :func:`core.randomness.gap_distribution_test` shows the gaps follow the
    geometric law of independence on this archive, which is the formal way of
    saying a number that has been absent for 100 draws is exactly as likely as
    one drawn last week.
    """
    gaps = current_gaps(draws)
    return {n: float(gaps[n]) for n in ALL_NUMBERS}


def random_scores(seed: int | None = None) -> dict[int, float]:
    """A score per number from a seeded generator: the control condition.

    Seeded rather than not, so a validation run is reproducible. An unseeded
    baseline that moves between runs cannot be distinguished from a method
    that moves between runs.
    """
    rng = random.Random(seed)
    return {n: rng.random() for n in ALL_NUMBERS}


def rank_numbers(scores: dict[int, float], descending: bool = True) -> list[int]:
    """The ninety numbers ordered by score, ties broken by the number itself.

    The tie-break is not cosmetic. The presence representation forecasts to
    near-identical values for every number, so without a deterministic order
    the ranking would depend on dictionary insertion and two identical runs
    would print different combinations.
    """
    return sorted(ALL_NUMBERS, key=lambda n: (-scores[n] if descending else scores[n], n))


# ─────────────────────────────────────────────────────────────
# Combinations
# ─────────────────────────────────────────────────────────────

def build_combinations(
    ranked: list[int], count: int = 5, size: int = NUMBERS_PER_DRAW
) -> list[tuple[int, ...]]:
    """``count`` combinations of ``size`` numbers, drawn from the top of the ranking.

    The first is the top ``size`` numbers. Each subsequent one slides one
    place down the ranking, so five combinations of six use the top ten
    numbers and overlap heavily — which is the honest thing for them to do.
    A method that ranks numbers has said the top ten are its best ten; making
    the five combinations disjoint would mean playing its 25th choice, and
    dressing up a wider net as five independent opinions.
    """
    if size > NUMBER_MAX:
        raise ValueError(f"cannot pick {size} numbers out of {NUMBER_MAX}")
    pool = ranked[: size + count - 1]
    if len(pool) < size:
        pool = ranked[:size]
    return [tuple(sorted(pool[i:i + size])) for i in range(min(count, len(pool) - size + 1))]


def predict(
    draws: list[Draw],
    method: str = "frequency",
    combinations: int = 5,
    size: int = NUMBERS_PER_DRAW,
    forecaster=None,
    window: int = DEFAULT_WINDOW,
    seed: int | None = None,
    progress=None,
) -> Prediction:
    """Produce a :class:`Prediction` with the named method.

    ``forecaster`` is required for ``"timesfm"`` and ignored otherwise, so a
    caller with no model can still exercise every other path — including the
    whole validation harness.
    """
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {', '.join(METHODS)}")

    if method == "timesfm":
        if forecaster is None:
            raise ValueError("the timesfm method needs a loaded TimesFMForecaster")
        scores = forecaster.score_numbers(draws, progress=progress)
        note = "TimesFM 3.0 one-step forecast of each number's series."
    elif method == "frequency":
        scores = frequency_scores(draws, window)
        note = f"Appearances in the last {min(window, len(draws))} draws."
    elif method == "gap":
        scores = gap_scores(draws)
        note = "Draws since each number last appeared."
    else:
        scores = random_scores(seed)
        note = "Seeded pseudo-random scores — the control condition."

    ranked = rank_numbers(scores)
    return Prediction(
        method=method,
        scores=scores,
        ranked=ranked,
        combinations=build_combinations(ranked, combinations, size),
        generated_at=datetime.now(timezone.utc),
        archive_last_date=draws[-1].date if draws else None,
        archive_size=len(draws),
        note=note,
    )


# ─────────────────────────────────────────────────────────────
# What a ticket is actually worth
# ─────────────────────────────────────────────────────────────

def category_odds(size: int = NUMBERS_PER_DRAW) -> dict[str, int]:
    """One-in-N odds for each prize category on a single ``size``-number line.

    Exact combinatorics on a 90-number wheel, six drawn plus a Jolly from the
    remaining 84:

    - ``"6"``   C(90,6) = 622,614,630 combinations, one of which wins.
    - ``"5+1"`` five of the six, and the sixth pick is the Jolly: 6 ways.
    - ``"5"``   five of the six, and the sixth pick is one of the other 83.
    - ``"4"``   C(6,4)·C(84,2).
    - ``"3"``   C(6,3)·C(84,3).
    - ``"2"``   C(6,2)·C(84,4) — pays only in the SuperStar game.

    These are facts about the wheel and hold whatever numbers are played. No
    ranking, ordering or system changes them, which is the single most useful
    sentence in this module.
    """
    if size != NUMBERS_PER_DRAW:
        raise ValueError("odds are defined for a plain six-number line")
    total = math.comb(NUMBER_MAX, NUMBERS_PER_DRAW)
    ways = {
        "6": 1,
        "5+1": math.comb(6, 5) * 1,
        "5": math.comb(6, 5) * (NUMBER_MAX - NUMBERS_PER_DRAW - 1),
        "4": math.comb(6, 4) * math.comb(NUMBER_MAX - NUMBERS_PER_DRAW, 2),
        "3": math.comb(6, 3) * math.comb(NUMBER_MAX - NUMBERS_PER_DRAW, 3),
        "2": math.comb(6, 2) * math.comb(NUMBER_MAX - NUMBERS_PER_DRAW, 4),
    }
    return {k: round(total / v) for k, v in ways.items()}


def expected_hits(size: int = NUMBERS_PER_DRAW) -> float:
    """Expected count of matching numbers on one line: ``size`` × 6 / 90.

    0.4 for a six-number line. Every method in this module has this as its
    expected score, and :mod:`core.validation` measures how far each one lands
    from it. None of them lands far.
    """
    return size * NUMBERS_PER_DRAW / NUMBER_MAX


def value_note() -> str:
    """The sentence the prediction panel prints under every set of numbers."""
    odds = category_odds()
    return (
        f"One line matches all six with probability 1 in {odds['6']:,}, and matches "
        f"three with probability 1 in {odds['3']:,}. Those odds are fixed by the wheel "
        "and no method of choosing numbers changes them. Prizes are pari-mutuel — a "
        "share of the stakes, not a fixed payout — so the operator keeps a fixed cut of "
        "every euro staked and the expected return on a line is below its price whatever "
        "is played. Tyche predicts nothing; it measures."
    )
