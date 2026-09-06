# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
power.py — Tyche

How small an edge would the validation harness actually notice?

The question this answers
-------------------------

Tyche reports that nothing beats chance. On its own that sentence is weak,
because it is also what a broken instrument says. "No method scored above
chance" and "this harness could not have detected an edge either way" produce
identical output, and the program had no way to tell a reader which one it
was looking at.

This module closes that gap by running the real harness against forecasters
whose edge is *known, because it was put there*. Each one sees the draw it is
being asked to predict and leaks some of it, in a controlled amount. At size
zero it is the random baseline; turn the size up and it becomes an oracle.
Running many times at each size gives the fraction of runs the harness would
have flagged — the statistical power — and the smallest size that reaches 80%
is the floor below which "we found nothing" stops meaning anything.

Three shapes, because the shape decides the answer
--------------------------------------------------

The first version of this module tested one shape and drew the wrong
conclusion from it. A real edge, if one existed, could sit anywhere in the
ranking, and the two metrics the harness reports are not sensitive to the
same places:

``concentrato``
    Each of the six drawn numbers is revealed outright with probability
    ``size``, jumping to the top of the ranking. The shape a leak would have.

``diffuso``
    All six drawn numbers get ``size`` added to their score, moving them up a
    few places each without usually reaching the top. The shape a weak but
    genuine signal would have.

``nascosto``
    The same nudge, but capped so a drawn number can never climb out of the
    bottom half. An edge that exists and never reaches the six numbers a
    player would actually bet on.

Measured on the 4,260-draw archive over 300 target draws, the hit count wins
on ``concentrato``, the two are close on ``diffuso``, and on ``nascosto`` the
hit count's z-score does not move *at all* — it is the identical number at
every size, because the top six never change. The rank statistic reaches
z = +11 on the same runs.

So the rank statistic is **not** a more sensitive version of the hit count,
which is what this module was written to demonstrate and is not what it
found. It is a complement that covers the one blind spot the hit count has by
construction. Both are reported, and neither is dropped.

What this is not
----------------

Not a method, and it must never become one. :data:`core.predictor.METHODS`
does not list these and nothing in ``gui/`` can reach them as forecasters:
they work only by reading ``draws[len(history)]``, the draw they are being
scored against, which is cheating by construction and is the entire point.
They are test instruments for the harness, in the same family as the oracle
in the test suite.

The floors this prints are also the *best* case. Three shapes are not every
shape, and a real edge that happened to fall between them would be harder to
see than the numbers here suggest, not easier.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from core.archive import ALL_NUMBERS, Draw
from core.validation import walk_forward

# Where a run counts as having raised a flag. One-sided: an edge makes a
# method score *better* than chance, and a method scoring worse is not a
# discovery, so spending half the alpha on that tail would only cost power.
ALPHA = 0.05

# The conventional bar for "the experiment was big enough to settle it".
TARGET_POWER = 0.80

# Repetitions per row. Every cell in the table is itself an estimate from a
# binomial sample, and the first draft of this defaulted to 20 — where the
# standard error is 11 percentage points. The size-zero control came out at
# 15% and looked like a broken metric; at 400 repetitions the same control is
# 5.2%, which is the nominal rate. Three out of twenty is not a calibration
# failure, it is noise, and a table too coarse to tell the two apart is worse
# than no table. 100 puts the standard error at 5 points or below.
DEFAULT_RUNS = 100

SHAPES = ("concentrato", "diffuso", "nascosto")

# Grids chosen so each shape's curve crosses TARGET_POWER inside the range.
# They are not comparable across shapes — a size of 0.05 means a different
# thing in each — which is why the report keeps the three tables apart.
DEFAULT_SIZES: dict[str, tuple[float, ...]] = {
    "concentrato": (0.0, 0.002, 0.005, 0.01, 0.02),
    "diffuso": (0.0, 0.005, 0.01, 0.02, 0.05),
    "nascosto": (0.0, 0.01, 0.02, 0.05, 0.10),
}


class _KnownEdge:
    """A forecaster that cheats by a measured amount.

    Shaped like :class:`core.forecaster.TimesFMForecaster` as far as the
    harness is concerned — one ``score_numbers(history)`` method — so the
    calibration drives the same code path a real model does, rather than a
    copy of it that could drift out of agreement with it.
    """

    def __init__(self, draws: list[Draw], shape: str, size: float, seed: int = 0) -> None:
        if shape not in SHAPES:
            raise ValueError(f"forma sconosciuta: {shape!r}; attese {', '.join(SHAPES)}")
        if size < 0.0:
            raise ValueError(f"la dimensione del vantaggio non puo' essere negativa: {size}")
        self.draws = draws
        self.shape = shape
        self.size = size
        self.seed = seed

    def score_numbers(self, history: list[Draw]) -> dict[int, float]:
        """Random scores for all ninety, with the target's six given an edge."""
        target = self.draws[len(history)]
        # A tuple is not an accepted seed, so the two numbers are combined
        # into one that keeps successive positions far apart.
        rng = random.Random(self.seed * 1_000_003 + len(history))
        scores = {n: rng.random() for n in ALL_NUMBERS}

        for n in target.numbers:
            if self.shape == "concentrato":
                # Above 1.0, so a leaked number outranks every other number.
                if rng.random() < self.size:
                    scores[n] += 1.0
            elif self.shape == "diffuso":
                scores[n] += self.size
            else:  # nascosto
                if scores[n] < 0.5:
                    # Capped just under the halfway mark: the number climbs,
                    # and provably never enters the top six.
                    scores[n] = min(scores[n] + self.size, 0.499)
        return scores


@dataclass(frozen=True)
class PowerPoint:
    """What the harness did against a known edge of one shape and size."""

    shape: str
    size: float
    runs: int
    hits_power: float
    rank_power: float
    mean_excess_hits: float
    mean_rank: float


def power_at(
    draws: list[Draw],
    shape: str,
    size: float,
    n_draws: int = 300,
    runs: int = DEFAULT_RUNS,
    seed: int = 0,
) -> PowerPoint:
    """Run the real harness ``runs`` times against an edge of that shape and size."""
    hits_flagged = 0
    rank_flagged = 0
    excess = 0.0
    rank = 0.0
    for r in range(runs):
        oracle = _KnownEdge(draws, shape, size, seed=seed + r * 1000)
        result = walk_forward(
            draws, methods=["timesfm"], n_draws=n_draws, forecaster=oracle,
        ).results[0]
        # One-sided at ALPHA: the harness reports a two-sided p, so halve it,
        # and only count the tail an edge would actually produce.
        if result.z > 0 and result.p_value / 2 < ALPHA:
            hits_flagged += 1
        if result.rank_z > 0 and result.rank_p / 2 < ALPHA:
            rank_flagged += 1
        excess += result.excess
        rank += result.mean_rank
    return PowerPoint(
        shape=shape,
        size=size,
        runs=runs,
        hits_power=hits_flagged / runs,
        rank_power=rank_flagged / runs,
        mean_excess_hits=excess / runs,
        mean_rank=rank / runs,
    )


def calibrate(
    draws: list[Draw],
    shapes: tuple[str, ...] = SHAPES,
    sizes: dict[str, tuple[float, ...]] | None = None,
    n_draws: int = 300,
    runs: int = DEFAULT_RUNS,
    seed: int = 0,
    progress=None,
) -> list[PowerPoint]:
    """The whole curve: power against edge size, for every shape and metric.

    The size-zero row of each shape is the one to read first. It is the
    false-positive rate and it has to come out near :data:`ALPHA`. A metric
    that flags a quarter of its runs against no edge at all is not sensitive,
    it is broken, and every other row of its column is worthless.
    """
    grid = sizes or DEFAULT_SIZES
    jobs = [(shape, size) for shape in shapes for size in grid[shape]]
    points = []
    for step, (shape, size) in enumerate(jobs):
        if progress:
            progress(f"Calibrazione {shape} a {size:.3f}…", step / len(jobs))
        points.append(
            power_at(draws, shape, size, n_draws=n_draws, runs=runs, seed=seed)
        )
    if progress:
        progress("Calibrazione completata.", 1.0)
    return points


def detection_floor(
    points: list[PowerPoint], shape: str, target: float = TARGET_POWER
) -> tuple[float | None, float | None]:
    """The smallest tested size at which each metric reaches ``target`` power.

    ``None`` where no tested size got there. That is a result rather than a
    failure: for the ``nascosto`` shape the hit count returns ``None`` at
    every size, which is the finding.
    """
    ordered = sorted((p for p in points if p.shape == shape), key=lambda p: p.size)
    hits = next((p.size for p in ordered if p.hits_power >= target), None)
    rank = next((p.size for p in ordered if p.rank_power >= target), None)
    return hits, rank


_SHAPE_NOTES = {
    "concentrato": "i sei numeri vengono rivelati con probabilita' pari alla dimensione",
    "diffuso": "i sei numeri salgono di qualche posto, di rado fino in cima",
    "nascosto": "i sei numeri salgono, ma non possono uscire dalla meta' bassa",
}


def report(points: list[PowerPoint], target: float = TARGET_POWER) -> str:
    """The calibration as the CLI and the Validate tab print it."""
    from core.scoring import MEAN_RANK

    if not points:
        return "Nessuna calibrazione eseguita."

    runs = points[0].runs
    # The worst-case standard error of a proportion, at p = 0.5.
    cell_se = (0.25 / runs) ** 0.5
    lines = [
        f"Potenza dell'esperimento — {runs} ripetizioni per riga, "
        f"ogni percentuale +/- {cell_se:.0%} circa.",
        "",
        "Con quanta frequenza la validazione si accorge di un vantaggio che",
        "sappiamo esserci, perche' ce l'abbiamo messo noi. La colonna che conta",
        "e' 'vista da', non l'entita' dello scarto.",
        "",
    ]

    for shape in SHAPES:
        rows = sorted((p for p in points if p.shape == shape), key=lambda p: p.size)
        if not rows:
            continue
        lines.append(f"{shape} — {_SHAPE_NOTES[shape]}")
        lines.append(
            f"  {'dimensione':>10}  {'centri':>8} {'vista da':>8}  "
            f"{'rango':>8} {'vista da':>8}"
        )
        for p in rows:
            lines.append(
                f"  {p.size:>10.3f}  {p.mean_excess_hits:>+8.1f} {p.hits_power:>7.0%}  "
                f"{p.mean_rank:>8.2f} {p.rank_power:>7.0%}"
            )
        hits_floor, rank_floor = detection_floor(points, shape, target)
        lines.append(
            f"  soglia al {target:.0%}: centri {_floor_text(hits_floor)}, "
            f"rango {_floor_text(rank_floor)}"
        )
        lines.append("")

    lines.append(
        f"Il caso vale 0 centri in eccesso e un rango medio di {MEAN_RANK:.1f}. "
        "Le righe a dimensione 0 non contengono alcun vantaggio: sono la"
    )
    lines.append(
        f"frequenza di falsi allarmi e devono restare vicine al {ALPHA:.0%}, "
        "altrimenti nessun'altra riga della stessa colonna vuole dire niente."
    )
    lines.append("")
    lines.append(
        "Le dimensioni non sono confrontabili fra forme diverse: 0,05 significa "
        "una cosa diversa in ciascuna delle tre."
    )
    return "\n".join(lines)


def _floor_text(value: float | None) -> str:
    return f">= {value:.3f}" if value is not None else "mai raggiunta"
