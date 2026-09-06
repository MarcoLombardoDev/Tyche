# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
predictor.py — Tyche

Turns a score per number into numbers to play, and says what that is worth.

Four methods, and the point of having four is that they can be compared:

- ``timesfm``    — the 330M foundation model of :mod:`core.forecaster`.
- ``frequenza``  — play the numbers drawn most often lately ("hot").
- ``ritardo``    — play the numbers absent longest, the method every Italian
  archive site's front page sells.
- ``casuale``    — six numbers from a seeded generator.

:mod:`core.validation` scores all four against the same draws. They come out
the same, because the thing they are ranking has no order. Keeping the naive
baselines in the product rather than in a footnote is what makes that
visible: a user who sees TimesFM tie with ``casuale`` has learned something a
paragraph of warning text cannot teach.

The odds functions are exact combinatorics, not estimates, and they are the
part of this module with unconditional value.
"""

from __future__ import annotations

import itertools
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from core.archive import ALL_NUMBERS, NUMBER_MAX, NUMBERS_PER_DRAW, Draw
from core.features import DEFAULT_WINDOW, counts, current_gaps
from core.localise import it_number

# The identifiers the CLI and the settings file use. The three baselines are
# Italian because the concepts are: "ritardo" is the word the game's players
# actually use, and translating the prose while leaving `gap` on the command
# line would be a product that speaks two languages. "timesfm" stays as it is
# — it is the name of a model, not a word.
METHODS = ("timesfm", "frequenza", "ritardo", "casuale")


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
    # How many numbers each combination holds. Six is a plain column; more is
    # a sistema integrale, and core.predictor.system_columns says what it costs.
    size: int = NUMBERS_PER_DRAW
    # The SuperStar pick, when one was asked for. None means the ticket does
    # not play it, which is not the same as playing it and getting zero.
    superstar: int | None = None

    def to_log_entry(self) -> dict:
        return {
            "method": self.method,
            "generated_at": self.generated_at.isoformat(),
            "archive_last_date": (
                self.archive_last_date.isoformat() if self.archive_last_date else None
            ),
            "archive_size": self.archive_size,
            "combinations": [list(c) for c in self.combinations],
            "size": self.size,
            "superstar": self.superstar,
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


def superstar_scores(draws: list[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """How often each number came up *as the SuperStar* in the last ``window``.

    The SuperStar comes out of its own drum, so it is a uniform draw from 90
    that is independent of the six and may repeat one of them — on the real
    archive it does so 247 times against 223 expected. That independence is
    why it gets its own scoring function rather than reusing the main one: a
    number can be cold on the wheel and hot on the SuperStar, and mixing the
    two counts would be an error of fact rather than of taste.

    Only draws that actually carry a SuperStar are counted. The game started
    on 28 March 2006 and the 914 draws before it store 0, which is "not on
    record"; treating those as a number would put a spike on nothing.
    """
    recorded = [d for d in draws if d.has_superstar]
    recent = recorded[-window:] if window else recorded
    total = max(len(recent), 1)
    tally = Counter(d.superstar for d in recent)
    return {n: tally[n] / total for n in ALL_NUMBERS}


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
        raise ValueError(f"non si possono scegliere {size} numeri su {NUMBER_MAX}")
    pool = ranked[: size + count - 1]
    if len(pool) < size:
        pool = ranked[:size]
    return [tuple(sorted(pool[i:i + size])) for i in range(min(count, len(pool) - size + 1))]


def predict(
    draws: list[Draw],
    method: str = "frequenza",
    combinations: int = 5,
    size: int = NUMBERS_PER_DRAW,
    forecaster=None,
    window: int = DEFAULT_WINDOW,
    seed: int | None = None,
    superstar: bool = False,
    progress=None,
) -> Prediction:
    """Produce a :class:`Prediction` with the named method.

    ``forecaster`` is required for ``"timesfm"`` and ignored otherwise, so a
    caller with no model can still exercise every other path — including the
    whole validation harness.

    ``size`` above six makes each combination a *sistema integrale*; ``size``
    is validated here so a bad setting fails at the point it is used rather
    than inside the combinatorics. ``superstar`` adds a SuperStar pick, scored
    from its own drum's history.
    """
    _check_system_size(size)
    if method not in METHODS:
        raise ValueError(
            f"metodo sconosciuto {method!r}; sono validi {', '.join(METHODS)}"
        )

    if method == "timesfm":
        if forecaster is None:
            raise ValueError(
            "il metodo timesfm richiede un TimesFMForecaster già caricato"
        )
        scores = forecaster.score_numbers(draws, progress=progress)
        note = "Previsione TimesFM 3.0 a un passo sulla serie di ogni numero."
    elif method == "frequenza":
        scores = frequency_scores(draws, window)
        note = f"Uscite nelle ultime {min(window, len(draws))} estrazioni."
    elif method == "ritardo":
        scores = gap_scores(draws)
        note = "Estrazioni trascorse dall'ultima uscita di ogni numero."
    else:
        scores = random_scores(seed)
        note = "Punteggi pseudo-casuali con seme fisso — la condizione di controllo."

    ranked = rank_numbers(scores)

    # The SuperStar is ranked by its own history, never by the main scores:
    # separate drum, separate question. The random baseline stays random here
    # too, so the control condition is a control on the whole ticket.
    star = None
    if superstar:
        if method == "casuale":
            star = rank_numbers(random_scores(seed))[0]
        else:
            star = rank_numbers(superstar_scores(draws, window))[0]

    return Prediction(
        method=method,
        scores=scores,
        ranked=ranked,
        combinations=build_combinations(ranked, combinations, size),
        generated_at=datetime.now(timezone.utc),
        archive_last_date=draws[-1].date if draws else None,
        archive_size=len(draws),
        note=note,
        size=size,
        superstar=star,
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


# A system of more than twelve numbers is 924 columns and climbing fast —
# C(14,6) is 3,003 — and the point of the cap is that the panel prints the
# column count beside it, so the cost is visible rather than discovered later.
SYSTEM_MIN = NUMBERS_PER_DRAW
SYSTEM_MAX = 12

# One in ninety, exactly, and independent of everything else on the ticket.
SUPERSTAR_ODDS = NUMBER_MAX


def system_columns(size: int = NUMBERS_PER_DRAW) -> int:
    """How many six-number columns a system of ``size`` numbers covers.

    C(size, 6): a *sistema integrale*, every combination of six from the
    numbers played. This is also what it costs, in units of one column.
    """
    _check_system_size(size)
    return math.comb(size, NUMBERS_PER_DRAW)


def system_top_prize_odds(size: int = NUMBERS_PER_DRAW) -> int:
    """One-in-N odds that a system of ``size`` numbers contains the six drawn.

    **The single most important number in this module, and not for the reason
    a player hopes.** Playing more numbers really does shorten these odds —
    from 1 in 622,614,630 on six numbers to 1 in 2,964,832 on ten. It also
    multiplies the cost by exactly the same factor, 210 columns instead of
    one, because the probability is ``C(size,6) / C(90,6)`` and the price is
    ``C(size,6)``. Divide one by the other at any size and the answer is
    always 622,614,630.

    A system buys probability strictly in proportion to money. It is a way of
    spending more, not a way of getting more per euro, and there is a test
    asserting that ratio stays constant across every size this module allows.
    """
    _check_system_size(size)
    return round(math.comb(NUMBER_MAX, NUMBERS_PER_DRAW) / system_columns(size))


def system_profile(size: int, matched: int) -> dict[int, int]:
    """``{numbers matched: winning columns}`` when ``matched`` of the six drawn
    fall inside a system of ``size`` numbers.

    This is what a system actually buys, and it is not only the top prize. Hit
    all six with a system of ten and the ticket does not hold one winning
    column, it holds one "6", twenty-four "5"s and a hundred and twenty "4"s —
    because every column that contains five of the six is also on the ticket.

    Exact, not simulated: columns holding exactly *j* of the drawn numbers are
    ``C(matched, j) · C(size - matched, 6 - j)``.

    The 5+1 category is deliberately absent. Whether a five-match column also
    takes the Jolly depends on the Jolly, which comes from the remaining 84
    numbers and is not part of the system.
    """
    _check_system_size(size)
    if not 0 <= matched <= NUMBERS_PER_DRAW:
        raise ValueError(f"si possono indovinare da 0 a 6 numeri, non {matched}")
    profile = {}
    for j in range(2, NUMBERS_PER_DRAW + 1):
        columns = math.comb(matched, j) * math.comb(size - matched, NUMBERS_PER_DRAW - j)
        if columns:
            profile[j] = columns
    return profile


def _check_system_size(size: int) -> None:
    if not SYSTEM_MIN <= size <= SYSTEM_MAX:
        raise ValueError(
            f"un sistema va da {SYSTEM_MIN} a {SYSTEM_MAX} numeri, non {size}"
        )


# What a play costs at the receiver, as of 2026. Both are settings, because
# they are set by the operator and not by arithmetic: if either changes, the
# user edits a number instead of waiting for a release.
DEFAULT_COLUMN_PRICE = 1.00
DEFAULT_SUPERSTAR_PRICE = 0.50


@dataclass(frozen=True)
class TicketCost:
    """What the combinations on screen would cost, and what they really cover."""

    plays: int
    size: int
    columns_paid: int
    columns_distinct: int
    superstar: bool
    total: float

    @property
    def duplicated(self) -> int:
        """Columns paid for more than once across the plays."""
        return self.columns_paid - self.columns_distinct


def distinct_columns(combinations: list[tuple[int, ...]]) -> int:
    """How many *different* six-number columns a set of plays actually covers.

    Not the same as what they cost. :func:`build_combinations` slides one
    place down the ranking for each play, so consecutive systems share most of
    their numbers and therefore most of their columns: five systems of twelve
    pay for 4,620 columns and cover 2,772 of them, wasting 40% of the stake on
    columns bought twice.

    A receiver charges per column submitted, so the duplicates really are paid
    for. Whether that is a mistake is the user's call — but they should be
    able to see it, which is why this is computed rather than assumed away.
    """
    seen = set()
    for play in combinations:
        seen.update(frozenset(c) for c in itertools.combinations(sorted(play), NUMBERS_PER_DRAW))
    return len(seen)


def ticket_cost(
    combinations: list[tuple[int, ...]],
    superstar: bool = False,
    column_price: float = DEFAULT_COLUMN_PRICE,
    superstar_price: float = DEFAULT_SUPERSTAR_PRICE,
) -> TicketCost:
    """Price the plays on screen, at the prices the settings carry.

    The SuperStar is charged per column, like the column itself, so adding it
    to a system multiplies its cost by the same factor as the system.
    """
    if not combinations:
        return TicketCost(0, NUMBERS_PER_DRAW, 0, 0, superstar, 0.0)
    size = len(combinations[0])
    paid = len(combinations) * system_columns(size)
    per_column = column_price + (superstar_price if superstar else 0.0)
    return TicketCost(
        plays=len(combinations),
        size=size,
        columns_paid=paid,
        columns_distinct=distinct_columns(combinations),
        superstar=superstar,
        total=round(paid * per_column, 2),
    )


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
        f"Una colonna fa 6 con probabilità 1 su {it_number(odds['6'])} e fa 3 con "
        f"probabilità 1 su {it_number(odds['3'])}. Queste probabilità sono fissate "
        "dalla ruota e nessun criterio di scelta dei numeri le cambia. I premi "
        "sono a totalizzatore — una quota della raccolta, non un importo fisso "
        "— quindi il concessionario "
        "trattiene una parte fissa di ogni euro giocato e il rendimento atteso di una "
        "colonna è inferiore al suo prezzo, qualunque cosa si giochi. Tyche non "
        "prevede nulla: misura."
    )
