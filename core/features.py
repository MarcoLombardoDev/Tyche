# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
features.py — Tyche

Turns a list of draws into the matrices the forecaster and the statistics read.

Everything here is shaped ``(90, T)`` — one row per number, one column per
draw, oldest column first. That is TimesFM 3.0's multivariate layout
``(num_variates, context_length)``, which is the whole reason Tyche targets
3.0 rather than 2.5: the ninety series can be handed to the model as one joint
context instead of ninety independent univariate calls, so whatever
cross-number structure the model can see, it gets the chance to see.

Three representations of the same history, because they are not
interchangeable:

- **presenza** is the raw fact: 1 if the number was drawn, 0 if not. Faithful,
  and almost pure noise at the single-draw level — the mean of any row is
  6/90 = 0.0667 and its autocorrelation is indistinguishable from zero.
- **frequenza** is presence smoothed over a trailing window. This is
  the series a forecaster can actually work with, because it has enough
  amplitude to carry a gradient, and it is also the one that invents structure
  most convincingly: a moving average of white noise looks like it has
  momentum. Every trend visible in it is an artefact of the window.
- **ritardo** is the Italian player's own term — draws since the number last
  came up. It rises by one per draw and resets to zero, so it is
  deterministic given presence and adds no information; it is here because it
  is what a player expects to see, and because its distribution is a clean
  test of independence (:mod:`core.randomness`).

None of the three makes the next draw predictable. They make it *describable*,
which is a different and more honest claim.
"""

from __future__ import annotations

import numpy as np

from core.archive import ALL_NUMBERS, NUMBER_MAX, Draw

# Trailing window for the frequency series, in draws: one year.
#
# **Counted off the archive rather than assumed, and the old value was a year
# that stopped existing.** 150 was "roughly a year at three draws a week",
# which the game drew until 2022 — 156, 157, 156, 157 a year through the
# 2010s. The schedule changed: 182 draws in 2023, then **208 in 2024 and 208
# in 2025**, which is four a week. A window of 150 is now about nine months,
# and nothing said so.
#
# 208 rather than 210: fifty-two weeks times four is what the archive counts,
# twice, exactly.
DEFAULT_WINDOW = 208


def presence_matrix(draws: list[Draw]) -> np.ndarray:
    """``(90, T)`` of 0/1 — was number *i+1* drawn in draw *t*.

    Float rather than int because every consumer, TimesFM included, wants
    float32, and converting once here beats converting in four places.
    """
    matrix = np.zeros((NUMBER_MAX, len(draws)), dtype=np.float32)
    for t, draw in enumerate(draws):
        for n in draw.numbers:
            matrix[n - 1, t] = 1.0
    return matrix


def rolling_frequency(presence: np.ndarray, window: int = DEFAULT_WINDOW) -> np.ndarray:
    """``(90, T)`` trailing mean of ``presence`` over ``window`` draws.

    The first ``window`` columns divide by however many draws exist so far
    rather than by ``window``, so the series starts at a real frequency
    instead of climbing out of an artificial zero. A forecaster fed the
    zero-padded version learns that ramp and reproduces it, which looks
    exactly like having learned something.
    """
    if window < 1:
        raise ValueError("la finestra deve essere almeno 1")
    n_numbers, n_draws = presence.shape
    if n_draws == 0:
        return presence.copy()
    cumulative = np.cumsum(presence, axis=1)
    padded = np.concatenate([np.zeros((n_numbers, 1), dtype=presence.dtype), cumulative], axis=1)
    starts = np.maximum(np.arange(n_draws) - window + 1, 0)
    sums = cumulative - padded[:, starts]
    counts = np.arange(n_draws) - starts + 1
    return (sums / counts).astype(np.float32)


def gap_matrix(presence: np.ndarray) -> np.ndarray:
    """``(90, T)`` of draws since each number last appeared, *before* draw t.

    Column ``t`` is what a player would have seen walking up to the terminal
    ahead of draw ``t``: a number drawn at ``t`` still shows its old gap
    there, and only resets at ``t+1``. Writing the reset into column ``t``
    would leak the outcome into the features, which is the standard way a
    backtest of this kind accidentally reports skill.
    """
    n_numbers, n_draws = presence.shape
    gaps = np.zeros((n_numbers, n_draws), dtype=np.float32)
    current = np.zeros(n_numbers, dtype=np.float32)
    for t in range(n_draws):
        gaps[:, t] = current
        drawn = presence[:, t] > 0
        current = current + 1.0
        current[drawn] = 0.0
    return gaps


def current_gaps(draws: list[Draw]) -> dict[int, int]:
    """Draws since each number last appeared, as of after the final draw.

    A number that has never appeared reports the full length of the archive,
    not zero — "never seen in 3,000 draws" and "seen last time" must not
    collapse to the same value.
    """
    last_seen = dict.fromkeys(ALL_NUMBERS)
    for t, draw in enumerate(draws):
        for n in draw.numbers:
            last_seen[n] = t
    total = len(draws)
    return {n: (total - 1 - t if t is not None else total) for n, t in last_seen.items()}


def counts(draws: list[Draw]) -> dict[int, int]:
    """How many times each number has been drawn across the whole archive."""
    tally = dict.fromkeys(ALL_NUMBERS, 0)
    for draw in draws:
        for n in draw.numbers:
            tally[n] += 1
    return tally


def pair_counts(draws: list[Draw]) -> dict[tuple[int, int], int]:
    """How often each unordered pair of numbers was drawn together.

    4,005 pairs against a few thousand draws, so the expected count per pair
    is well under ten and the extremes are dominated by noise. The panel that
    shows this says so; the function does not editorialise.
    """
    tally: dict[tuple[int, int], int] = {}
    for draw in draws:
        nums = draw.numbers
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                key = (nums[i], nums[j])
                tally[key] = tally.get(key, 0) + 1
    return tally


def decade_profile(draw: Draw) -> list[int]:
    """Count of the six numbers falling in 1–10, 11–20, … 81–90.

    Nine bands of exactly ten, which is the one thing worth checking before
    comparing their counts: 90 divides evenly, so every band has the same
    expectation and no weighting is needed. Bands of 1–9, 10–19, … 80–90 are
    also nine, are the way the boundaries are often drawn, and are *not*
    equal — the first holds nine numbers and the last eleven. Mixing the two
    conventions is how "the eighties are hot" gets asserted from a table where
    the eighties simply had more numbers in them.
    """
    buckets = [0] * 9
    for n in draw.numbers:
        buckets[(n - 1) // 10] += 1
    return buckets


def superstar_presence_matrix(draws: list[Draw]) -> np.ndarray:
    """``(90, drawn)`` 0/1 over the SuperStar's *own* drum.

    Only draws that carry one. The game began on 28 March 2006 and every draw
    before it stores 0 for "not on record": including those columns would
    teach a forecaster nine hundred draws in which no number was ever the
    SuperStar, which is a fact about the archive and not about the drum.
    """
    recorded = [d for d in draws if d.has_superstar]
    matrix = np.zeros((NUMBER_MAX, len(recorded)), dtype=np.float32)
    for column, draw in enumerate(recorded):
        matrix[draw.superstar - 1, column] = 1.0
    return matrix


def _view(
    presence: np.ndarray,
    representation: str,
    window: int,
    context_length: int | None,
) -> np.ndarray:
    """One of the three views of a presence matrix, trimmed and ready."""
    if representation == "presenza":
        series = presence
    elif representation == "frequenza":
        series = rolling_frequency(presence, window)
    elif representation == "ritardo":
        series = gap_matrix(presence)
    else:
        raise ValueError(f"rappresentazione sconosciuta: {representation!r}")
    if context_length is not None and series.shape[1] > context_length:
        series = series[:, -context_length:]
    return np.ascontiguousarray(series, dtype=np.float32)


def build_context(
    draws: list[Draw],
    representation: str = "frequenza",
    window: int = DEFAULT_WINDOW,
    context_length: int | None = None,
) -> np.ndarray:
    """``(90, context_length)`` float32 ready for TimesFM.

    ``representation`` picks which of the three views above to hand the model.
    ``context_length`` trims to the most recent columns; None keeps everything.
    """
    return _view(presence_matrix(draws), representation, window, context_length)


def build_superstar_context(
    draws: list[Draw],
    representation: str = "frequenza",
    window: int = DEFAULT_WINDOW,
    context_length: int | None = None,
) -> np.ndarray:
    """The same three views, over the SuperStar's drum instead of the wheel.

    Separate from :func:`build_context` rather than a flag on it, because the
    two answer different questions about different urns and a caller that got
    the flag wrong would get a plausible-looking forecast of the wrong thing.
    """
    return _view(
        superstar_presence_matrix(draws), representation, window, context_length
    )
