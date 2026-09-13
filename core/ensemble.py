# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
ensemble.py — Tyche

The fifth method: one ranking of the ninety numbers, combined from the other
three, with weights the archive decided rather than weights somebody chose.

Why the weights are measured and not written down
-------------------------------------------------

A weighted average of three rankings needs three numbers, and every way of
picking them by hand is an assertion about which method knows more. Tyche is
in no position to make that assertion — the whole of :mod:`core.validation`
says the three score the same — and a hardcoded ``0.6`` on TimesFM would be
the program asserting about itself the exact thing the rest of it refuses to
assert. So the weights come out of a walk-forward backtest over the recent
archive: each candidate weighting is scored on draws it never saw while it
was being chosen, and the best one wins.

**TimesFM can end up at zero, and nothing here prevents it.** There is no
floor under any component. On this data the model's forecast is very nearly
flat across the ninety numbers — 1.1% each, to four decimals — so its
distribution carries almost no ordering information, and a mixture is linear:
a flat component moves the blend by almost nothing whatever weight it is
given. The fit will notice that, and the report says so in as many words
through the informativeness column. That is the honest outcome and it must
not be papered over.

What the components are
-----------------------

The three are the ones the program already computes, reused rather than
reimplemented:

``timesfm``    :meth:`core.forecaster.TimesFMForecaster.score_numbers`
``ritardo``    :func:`core.predictor.gap_scores`
``frequenza``  :func:`core.predictor.frequency_scores` over the configured window

``casuale`` is measured alongside them as a control — never as a component —
for the same reason the Prediction panel keeps its cell: a comparison whose
baseline is missing is not a comparison.

The scale they are put on
-------------------------

The three raw scores are a rate, a count of draws and a forecast of a 0/1
series. They cannot be added as they are, so each is turned into a
distribution over the ninety numbers: non-negative, summing to one.

**The normalisation is deliberately the boring one** — divide by the sum,
shifting first only if some score is negative, which is the minimum needed to
have a distribution at all. Nothing rescales, centres, or exponentiates a
component to "make it competitive". A softmax with a temperature would turn
TimesFM's fourth-decimal differences into a confident-looking ranking, and
that temperature, not the model, would be doing the work. If a component is
flat it stays flat, and :func:`informativeness` measures how flat.

A consequence worth stating, because it looks like a bug and is not: a weight
is a weight on a *distribution*, not on an opinion. All three distributions
have the same mean, 1/90, so what a component contributes is its deviation
from uniform multiplied by its weight. ``ritardo`` spreads its mass much more
widely than TimesFM does, so at equal weights it moves the blend much more.
That is a fact about the components and the fit measures the mixture, not the
weight, so it comes out right — but reading "TimesFM 20%" as "a fifth of the
answer is TimesFM" would be wrong.

These distributions are **not calibrated probabilities**, and nothing here
scores them as if they were. Six numbers are drawn from ninety, so a
probability of being drawn would have to sum to six rather than to one, and
the number that turned a ranking into a probability would be a free parameter
fitted on something. Log loss and the Brier score are therefore absent for
the same reason :mod:`core.scoring` gives: they would measure the conversion.

No look-ahead, and how that is enforced
---------------------------------------

Every distribution in a backtest is computed from ``draws[:i]`` and scored
against ``draws[i]``. The target's own numbers reach only the scoring, never
a scorer. Two things follow that are easy to get wrong and are tested:

- **The weights are fitted on older targets than the ones they are judged
  on.** The fit splits the backtest in two: a train slice where the grid
  search runs, and a later validation slice it never sees. Every figure
  offered as evidence comes from the validation slice.
- **The rolling check refits as it goes.** :func:`rolling` walks the
  validation slice scoring each target with weights fitted only on targets
  before it, refitting every :data:`REFIT_EVERY` draws. That is the procedure
  as it would really be run, measured end to end, and it is the number to
  read if only one is read.

The weights offered for the *next* draw are then refitted on every target
available, train and validation together — the procedure having been
validated, there is no reason to throw away the newest evidence when applying
it. Both weightings are reported, and they are usually close.

What it costs
-------------

The cheap components are microseconds per target. TimesFM is one forward
pass — tens of seconds on a CPU — so a hundred-draw backtest with the model
in it is an hour of work. :class:`TraceCache` is why that is paid once: the
per-target distributions are stored by draw, so a refit after four new draws
costs four forward passes and not a hundred. The grid search itself never
re-runs a component; it re-scores the stored distributions, which is also
what makes every candidate weighting comparable — they are judged on
identical inputs.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from core.archive import ALL_NUMBERS, NUMBER_MAX, NUMBERS_PER_DRAW, Draw
from core.features import DEFAULT_WINDOW
from core.predictor import (
    frequency_scores,
    gap_scores,
    method_name,
    random_scores,
    rank_numbers,
    superstar_gap_scores,
    superstar_scores,
)
from core.scoring import MEAN_RANK, mid_ranks, rank_null_variance
from core.stats_tests import two_sided_normal_p
from core.validation import MIN_HISTORY

# The identifier of the combined method, as it appears in METHODS, in
# settings.json and on the command line.
ENSEMBLE = "ensemble"

# What goes into the blend. The order is the order the tables print in; it is
# the owner's order — the model first, then the two the game's own players
# use — and nothing else depends on it.
COMPONENTS = ("timesfm", "ritardo", "frequenza")

# Measured beside the components and never one of them. A control that can be
# chosen is not a control.
CONTROL = "casuale"

# The grid the weights are searched on, in steps of this size over the
# simplex. 0.05 gives 231 candidates for three components, each of which is
# re-scored over the stored distributions in a few milliseconds. A finer grid
# would report a precision the backtest does not have: over a hundred draws
# the noise on the objective is far wider than the difference between 0.35
# and 0.40.
WEIGHT_STEP = 0.05

# Where the hit counts are taken. 5, 10, 15, 20 and 30 are the requested
# gauges; 6 is kept because it is the one the rest of the program quotes —
# a played column is six numbers and chance is 0.4 of them — and dropping it
# would leave this report unable to be compared with --validate's.
TOP_K = (5, NUMBERS_PER_DRAW, 10, 15, 20, 30)

# How much worse than the best a weighting may score and still count as "the
# data cannot tell these two apart", in standard errors of the *paired*
# difference between the two.
#
# Paired, and that word is doing all the work. Two weightings are scored on
# the same draws, so the quantity with a meaningful error bar is the
# difference between them draw by draw, not each one's mean against chance.
# Two blends that order the ninety numbers almost identically differ by almost
# nothing on every draw — their paired error is tiny and a real gap between
# them survives it. Two blends that order them differently differ wildly draw
# by draw, and a gap of half a position between their averages is then
# indistinguishable from noise, because it is.
#
# One standard error, rather than the two a significance test would take: this
# is not a test of anything, it is the line between "measured" and "not
# measured", and drawing it generously would hand more of the answer to the
# tie-break below.
TOLERANCE_SIGMAS = 1.0

# The share of the blend a component must actually account for before a weight
# is reported for it at all.
#
# **This is the identifiability rule, and without it the weights table prints
# noise as a measurement.** A blend is linear and every component's
# distribution has the same mean, 1/90, so what a component contributes to the
# *order* is its deviation from uniform times its weight. A perfectly flat
# component contributes nothing at any weight: adding the same amount to all
# ninety scores leaves the ranking exactly where it was. The objective is then
# constant along that component's axis, the grid search is choosing between
# indistinguishable candidates, and whichever it happens to reach first gets
# printed — the first version of this module reported 55% for a component that
# could not have earned one basis point of it.
#
# So a component whose influence — its weight times its average distance from
# uniform, as a share of the whole blend's — comes out below this is set to
# zero and its weight redistributed. On Tyche's own data TimesFM lands near
# 1%, the other two between 20% and 80%, so the threshold sits in an empty
# gap rather than anywhere delicate.
#
# It is **not** a performance rule and must not be read as one. What decides
# how much weight a component gets is the backtest; this only refuses to
# report a weight that the backtest could not have measured.
MIN_INFLUENCE = 0.02

# How often the rolling check refits while walking the validation slice.
# Every draw would be the purest form of the procedure and would multiply the
# grid searches by the length of the slice for a difference smaller than the
# noise; ten is about a fortnight of draws.
REFIT_EVERY = 10

# How far the archive may move past a stored fit before it is refitted. Ten
# draws is two and a half weeks at the current schedule, and with the trace
# cache a refit then costs ten forward passes rather than a hundred.
REFIT_AFTER = 10

# The defaults for how long the backtest is. They are settings, because the
# cost is entirely the user's machine's: see DEFAULT_SETTINGS.
DEFAULT_BACKTEST_DRAWS = 120
DEFAULT_VALIDATION_DRAWS = 40


def _null_mrr() -> float:
    """Expected reciprocal of the best rank among six numbers drawn at random.

    Exact rather than simulated: the best of the six sits at rank *m* with
    probability ``C(90-m, 5) / C(90, 6)``. Printed beside the measured MRR so
    the number has something to be compared with — on its own, 0.19 says
    nothing at all.
    """
    total = math.comb(NUMBER_MAX, NUMBERS_PER_DRAW)
    return sum(
        math.comb(NUMBER_MAX - m, NUMBERS_PER_DRAW - 1) / total / m
        for m in range(1, NUMBER_MAX - NUMBERS_PER_DRAW + 2)
    )


NULL_MRR = _null_mrr()


# ─────────────────────────────────────────────────────────────
# Putting three different quantities on one scale
# ─────────────────────────────────────────────────────────────

def distribution(scores: dict[int, float]) -> dict[int, float]:
    """A score vector as a distribution over the ninety numbers.

    Non-negative and summing to one, by dividing by the total. A negative
    score — TimesFM can forecast one, the other two cannot — shifts the whole
    vector up by the minimum first, which is the least that can be done to
    make a distribution out of it.

    A vector with no spread at all comes back uniform rather than raising: a
    method that says nothing must be allowed to say nothing.
    """
    floor = min(scores.values()) if scores else 0.0
    shift = -floor if floor < 0 else 0.0
    total = sum(v + shift for v in scores.values())
    if total <= 0:
        return dict.fromkeys(ALL_NUMBERS, 1.0 / NUMBER_MAX)
    return {n: (scores[n] + shift) / total for n in ALL_NUMBERS}


@dataclass(frozen=True)
class Informativeness:
    """How far a component's distribution is from saying nothing.

    ``entropy`` is the Shannon entropy over the ninety numbers divided by
    ``log 90``, so 1.0 is exactly uniform and lower means more concentrated.
    ``candidates`` is ``exp(H)``: the number of equally-likely numbers the
    distribution is worth, which is 90 for a flat one. ``distance`` is the
    total variation distance from uniform, the share of the mass that would
    have to be moved to flatten it.

    **This measures discrimination, not skill**, and the distinction is the
    whole point. A component can be sharply concentrated and wrong; the
    backtest is what says whether the concentration is worth anything. It is
    reported because a near-uniform component and a useful one must not look
    the same in the weights table.
    """

    entropy: float
    candidates: float
    distance: float


def informativeness(dist: dict[int, float]) -> Informativeness:
    """:class:`Informativeness` of one distribution."""
    entropy = -sum(p * math.log(p) for p in dist.values() if p > 0)
    uniform = 1.0 / NUMBER_MAX
    return Informativeness(
        entropy=entropy / math.log(NUMBER_MAX),
        candidates=math.exp(entropy),
        distance=0.5 * sum(abs(p - uniform) for p in dist.values()),
    )


# ─────────────────────────────────────────────────────────────
# Weights
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Weights:
    """One weighting of the components: non-negative, summing to one."""

    values: dict[str, float]

    def __post_init__(self) -> None:
        if any(w < 0 for w in self.values.values()):
            raise ValueError(f"un peso non può essere negativo: {self.values}")
        total = sum(self.values.values())
        if self.values and abs(total - 1.0) > 1e-6:
            raise ValueError(f"i pesi devono sommare a 1, non a {total:.6f}")

    def of(self, component: str) -> float:
        return self.values.get(component, 0.0)

    @property
    def used(self) -> tuple[str, ...]:
        """The components that really take part — weight strictly above zero."""
        return tuple(c for c in self.values if self.values[c] > 0)

    def describe(self) -> str:
        return "  ".join(
            f"{method_name(c)} {self.values[c]:.0%}" for c in self.values
        )

    def as_record(self) -> dict[str, float]:
        return {c: round(w, 6) for c, w in self.values.items()}


def equal_weights(components: tuple[str, ...]) -> Weights:
    """The 1/n weighting: what the fit has to beat to have earned itself."""
    return Weights({c: 1.0 / len(components) for c in components})


def only(component: str) -> Weights:
    """The weighting that is one component and nothing else — a baseline."""
    return Weights({component: 1.0})


def weight_grid(components: tuple[str, ...], step: float = WEIGHT_STEP) -> list[Weights]:
    """Every weighting on the simplex at the given step, in a fixed order.

    A grid rather than a gradient method: the objective is a rank statistic
    over a few dozen draws, so it is not smooth, has no useful derivative and
    is cheap to evaluate. 231 exhaustive evaluations are both faster to write
    and easier to check than any optimiser, and they cannot land in a local
    minimum.
    """
    steps = round(1.0 / step)
    if steps <= 0 or abs(steps * step - 1.0) > 1e-9:
        raise ValueError(f"il passo {step} non divide 1")
    grid: list[Weights] = []

    def walk(index: int, left: int, taken: list[int]) -> None:
        if index == len(components) - 1:
            counts = taken + [left]
            grid.append(Weights({
                c: round(k / steps, 6) for c, k in zip(components, counts, strict=True)
            }))
            return
        for k in range(left + 1):
            walk(index + 1, left - k, taken + [k])

    if components:
        walk(0, steps, [])
    return grid


# ─────────────────────────────────────────────────────────────
# The walk-forward traces
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Trace:
    """One target draw, every component's distribution *before* it, and it.

    ``actual`` is the six numbers that came out. It is in here so the scoring
    has something to score against, and it is never handed to a component:
    the distributions were built from :attr:`history_size` earlier draws and
    the constructor of this object is the first place the two meet.
    """

    index: int
    draw_id: str
    draw_date: date
    history_size: int
    actual: frozenset[int]
    distributions: dict[str, dict[int, float]]


def _ask(scorer, history: list[Draw], progress):
    """Call a forecaster's scorer, passing ``progress`` only if there is one.

    The harness's forecasters are duck-typed — :class:`core.power._KnownEdge`
    and the test oracle are two of them — and the shape they are all promised
    to have is ``score_numbers(history)``. Handing them a keyword they never
    agreed to would mean the calibration instruments could not be run through
    the ensemble, which is exactly where a leaked edge needs to be run.
    """
    return scorer(history, progress=progress) if progress is not None else scorer(history)


def component_scores(
    history: list[Draw],
    components: tuple[str, ...],
    window: int = DEFAULT_WINDOW,
    forecaster=None,
    seed: int = 0,
    progress=None,
) -> dict[str, dict[int, float]]:
    """What each component scores the ninety numbers, given only ``history``.

    Raw scores, on each component's own scale — :func:`distribution` is what
    puts them on a common one. A component whose weight is zero should not be
    asked for at all, which is why the caller passes the list: skipping
    TimesFM is the difference between a forecast that takes a second and one
    that takes a minute.
    """
    scores: dict[str, dict[int, float]] = {}
    for component in components:
        if component == "timesfm":
            if forecaster is None:
                continue
            scores[component] = _ask(forecaster.score_numbers, history, progress)
        elif component == "ritardo":
            scores[component] = gap_scores(history)
        elif component == "frequenza":
            scores[component] = frequency_scores(history, window)
        elif component == CONTROL:
            scores[component] = random_scores(seed)
        else:
            raise ValueError(f"componente sconosciuto: {component!r}")
    return scores


def superstar_component_scores(
    history: list[Draw],
    components: tuple[str, ...],
    window: int = DEFAULT_WINDOW,
    forecaster=None,
    seed: int = 0,
    progress=None,
) -> dict[str, dict[int, float]]:
    """The same three questions asked of the SuperStar's own drum.

    Separate from the wheel because the urns are separate — a number can be
    cold on one and hot on the other — but blended with the *same* weights.
    Fitting a second set on the SuperStar would mean a second backtest over a
    single number per draw, which is six times less evidence for a quantity
    that has no reason to differ.
    """
    scores: dict[str, dict[int, float]] = {}
    for component in components:
        if component == "timesfm":
            if forecaster is None:
                continue
            scores[component] = _ask(forecaster.score_superstar, history, progress)
        elif component == "ritardo":
            scores[component] = superstar_gap_scores(history)
        elif component == "frequenza":
            scores[component] = superstar_scores(history, window)
        elif component == CONTROL:
            scores[component] = random_scores(seed)
        else:
            raise ValueError(f"componente sconosciuto: {component!r}")
    return scores


def blend(
    scores: dict[str, dict[int, float]], weights: Weights
) -> dict[int, float]:
    """The weighted mixture of the components' distributions.

    Components missing from ``scores`` — TimesFM on a machine with no model —
    are dropped and the remaining weights are renormalised, so the result is
    still a distribution and still in the same proportions as the fit found.
    A caller that wanted to know is told by :func:`missing`, rather than by
    the blend quietly becoming something else.
    """
    present = {c: w for c, w in weights.values.items() if w > 0 and c in scores}
    total = sum(present.values())
    if not present or total <= 0:
        return dict.fromkeys(ALL_NUMBERS, 1.0 / NUMBER_MAX)
    parts = {c: distribution(scores[c]) for c in present}
    return {
        n: sum(parts[c][n] * w for c, w in present.items()) / total
        for n in ALL_NUMBERS
    }


def missing(scores: dict[str, dict[int, float]], weights: Weights) -> tuple[str, ...]:
    """Components the weighting wants and the caller could not supply."""
    return tuple(c for c, w in weights.values.items() if w > 0 and c not in scores)


class TraceCache:
    """Per-draw component distributions, kept so a refit is not a re-run.

    Keyed by the draw the distribution predicts *and* by the length of the
    history it was built from, because an archive whose older rows were
    repaired is a different history under the same draw id. The parameters
    that change what a component answers — the frequency window, and the
    checkpoint and context length for TimesFM — are part of the file's
    fingerprint and a change to any of them empties it.

    Only TimesFM is worth caching; the other two are recomputed in
    microseconds and a stale copy of them would be a way to be wrong for no
    saving. :data:`CACHED` says so in one place.
    """

    CACHED = ("timesfm",)

    def __init__(self, path: Path | None = None, fingerprint: dict | None = None):
        self.path = Path(path) if path else None
        self.fingerprint = fingerprint or {}
        self.entries: dict[str, dict[int, float]] = {}
        self.hits = 0
        self.misses = 0
        self._dirty = False
        self._load()

    def _key(self, component: str, trace_key: str, history_size: int) -> str:
        return f"{component}|{trace_key}|{history_size}"

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(stored, dict) or stored.get("fingerprint") != self.fingerprint:
            return
        entries = stored.get("entries", {})
        if isinstance(entries, dict):
            self.entries = {
                key: {int(n): float(p) for n, p in value.items()}
                for key, value in entries.items()
                if isinstance(value, dict)
            }

    def get(self, component: str, trace_key: str, history_size: int):
        if component not in self.CACHED:
            return None
        found = self.entries.get(self._key(component, trace_key, history_size))
        if found is None:
            self.misses += 1
        else:
            self.hits += 1
        return found

    def put(
        self, component: str, trace_key: str, history_size: int,
        scores: dict[int, float],
    ) -> None:
        if component not in self.CACHED:
            return
        self.entries[self._key(component, trace_key, history_size)] = dict(scores)
        self._dirty = True

    def save(self) -> None:
        """Write the cache back, if there is anywhere to write it and anything new."""
        if not self.path or not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fingerprint": self.fingerprint,
            "entries": {
                key: {str(n): round(p, 8) for n, p in value.items()}
                for key, value in self.entries.items()
            },
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self.path)
        self._dirty = False


def _trace_key(draw: Draw) -> str:
    return f"{draw.draw_id}@{draw.date.isoformat()}"


def build_traces(
    draws: list[Draw],
    targets: list[int],
    components: tuple[str, ...],
    window: int = DEFAULT_WINDOW,
    forecaster=None,
    seed: int = 0,
    cache: TraceCache | None = None,
    progress=None,
) -> list[Trace]:
    """One :class:`Trace` per target, oldest first.

    This is the only place in the module that looks at the archive, and it is
    where the absence of look-ahead is enforced: the scorers are handed
    ``draws[:i]`` and the target's numbers are read afterwards, into a field
    nothing but the scoring reads. Everything downstream — the grid search,
    the baselines, the rolling refit — works from these objects and cannot
    reach the archive at all.
    """
    wanted = tuple(components) + (CONTROL,)
    traces: list[Trace] = []
    for step, i in enumerate(targets):
        history = draws[:i]
        target = draws[i]
        key = _trace_key(target)
        raw: dict[str, dict[int, float]] = {}
        for component in wanted:
            stored = cache.get(component, key, len(history)) if cache else None
            if stored is not None:
                raw[component] = stored
                continue
            computed = component_scores(
                history, (component,), window=window, forecaster=forecaster,
                seed=seed + i,
            )
            if component not in computed:
                continue
            raw[component] = computed[component]
            if cache:
                cache.put(component, key, len(history), computed[component])
        traces.append(Trace(
            index=i,
            draw_id=target.draw_id,
            draw_date=target.date,
            history_size=len(history),
            actual=frozenset(target.numbers),
            distributions={c: distribution(v) for c, v in raw.items()},
        ))
        if progress and (step % 2 == 0 or step == len(targets) - 1):
            progress(
                f"Backtest dell'ensemble: estrazione {step + 1} di {len(targets)}…",
                step / max(len(targets), 1),
            )
    if cache:
        cache.save()
    return traces


# ─────────────────────────────────────────────────────────────
# Scoring a weighting
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Performance:
    """What one weighting scored over one set of targets.

    ``mean_rank`` is the headline and the objective the search minimises: the
    average mid-rank of the six numbers that came out, where 45.5 is chance.
    It reads the whole ranking, which is why it is the objective — the hit
    counts throw away 84 numbers per draw and over a few dozen draws they are
    almost all noise. :mod:`core.power` measures exactly how much finer the
    rank gauge is, and the answer is "enough to matter here".

    The hit counts are reported all the same, at every requested *k*, because
    they are what a player would experience and the two must be seen to agree.
    """

    label: str
    weights: Weights
    draws_scored: int
    mean_rank: float
    rank_z: float
    rank_p: float
    mrr: float
    hits_at: dict[int, int]
    rate_at: dict[int, float]
    expected_hits_at: dict[int, float]
    expected_rate_at: dict[int, float]
    mean_entropy: float

    @property
    def objective(self) -> float:
        """Lower is better. The mean rank, and nothing else is fitted on."""
        return self.mean_rank

    def summary(self) -> str:
        hits = self.hits_at.get(NUMBERS_PER_DRAW, 0)
        per_draw = hits / self.draws_scored if self.draws_scored else 0.0
        return (
            f"{self.label:<22} rango {self.mean_rank:6.2f} (caso {MEAN_RANK:.1f}), "
            f"z = {self.rank_z:+5.2f}, centri su 6 {per_draw:.3f}, "
            f"MRR {self.mrr:.3f}"
        )


def _expected_rate(k: int) -> float:
    """Chance of at least one of the six falling in a fixed top *k*."""
    if k >= NUMBER_MAX - NUMBERS_PER_DRAW:
        return 1.0
    return 1.0 - math.comb(NUMBER_MAX - k, NUMBERS_PER_DRAW) / math.comb(
        NUMBER_MAX, NUMBERS_PER_DRAW
    )


def evaluate(
    traces: list[Trace],
    weights: Weights | list[Weights],
    label: str = "",
    tops: tuple[int, ...] = TOP_K,
) -> Performance:
    """Score a weighting — or a weighting per target — over the traces.

    The per-target list is what :func:`rolling` uses: each draw judged with
    the weights that were current when it was still in the future.
    """
    per_trace = weights if isinstance(weights, list) else [weights] * len(traces)
    if len(per_trace) != len(traces):
        raise ValueError("un peso per estrazione, o uno solo per tutte")

    n = max(len(traces), 1)
    rank_sum = 0.0
    rank_var = 0.0
    reciprocal = 0.0
    entropy = 0.0
    hits = dict.fromkeys(tops, 0)
    reached = dict.fromkeys(tops, 0)

    for trace, weighting in zip(traces, per_trace, strict=True):
        scores = blend(trace.distributions, weighting)
        entropy += informativeness(scores).entropy
        ranks = mid_ranks(scores)
        drawn = sorted(trace.actual)
        rank_sum += sum(ranks[x] for x in drawn) / len(drawn)
        rank_var += rank_null_variance(ranks, len(drawn))
        reciprocal += 1.0 / min(ranks[x] for x in drawn)
        order = sorted(scores, key=lambda x: (-scores[x], x))
        for k in tops:
            hit = len(trace.actual & set(order[:k]))
            hits[k] += hit
            reached[k] += 1 if hit else 0

    rank_sd = rank_var ** 0.5
    rank_z = (MEAN_RANK * len(traces) - rank_sum) / rank_sd if rank_sd > 0 else 0.0
    return Performance(
        label=label,
        weights=per_trace[-1] if per_trace else Weights({}),
        draws_scored=len(traces),
        mean_rank=rank_sum / n,
        rank_z=rank_z,
        rank_p=two_sided_normal_p(rank_z),
        mrr=reciprocal / n,
        hits_at=dict(hits),
        rate_at={k: reached[k] / n for k in tops},
        expected_hits_at={k: len(traces) * NUMBERS_PER_DRAW * k / NUMBER_MAX for k in tops},
        expected_rate_at={k: _expected_rate(k) for k in tops},
        mean_entropy=entropy / n,
    )


def _vectorise(
    traces: list[Trace], components: tuple[str, ...]
) -> list[tuple[list[list[float]], list[int]]]:
    """The traces as plain lists, for the one loop that runs 231 times.

    The grid search evaluates every candidate over every trace, so the inner
    loop is the only place in this module where speed is worth any words at
    all. Dictionaries keyed by number are the right shape for everything that
    is read once; here they are two hundred thousand lookups.
    """
    prepared = []
    for trace in traces:
        vectors = [
            [trace.distributions[c][n] for n in ALL_NUMBERS]
            for c in components
            if c in trace.distributions
        ]
        prepared.append((vectors, [n - 1 for n in sorted(trace.actual)]))
    return prepared


def _rank_series(
    prepared: list[tuple[list[list[float]], list[int]]], weights: list[float]
) -> list[float]:
    """The mean mid-rank of the drawn numbers, one value per trace.

    The same quantity :func:`evaluate` reports as ``mean_rank``, computed
    without building a ranking of all ninety: a number's mid-rank is one plus
    how many score above it plus half of how many tie with it, and only six
    numbers per draw are asked for. ``test_the_fast_objective_is_the_slow_one``
    holds the two to the same answer, because a search that optimises
    something subtly different from what the report prints would be the worst
    kind of wrong here.
    """
    series = []
    for vectors, drawn in prepared:
        blended = [
            sum(w * v[i] for w, v in zip(weights, vectors, strict=True))
            for i in range(NUMBER_MAX)
        ]
        total = 0.0
        for i in drawn:
            value = blended[i]
            above = 0
            equal = 0
            for other in blended:
                if other > value:
                    above += 1
                elif other == value:
                    equal += 1
            total += above + 1 + (equal - 1) / 2
        series.append(total / len(drawn))
    return series


def influence(traces: list[Trace], weights: Weights) -> dict[str, float]:
    """Each component's share of how far the blend departs from uniform.

    Not the same thing as its weight, and the difference is the point. A
    component contributes ``weight × distance from uniform``; ``ritardo``
    spreads its mass three times as widely as ``frequenza`` does, so at equal
    weights it does most of the ordering. Printed beside the weights so that
    "TimesFM 20%" cannot be read as "a fifth of this answer is TimesFM".
    """
    pull = {}
    for component in weights.used:
        measured = [
            informativeness(t.distributions[component]).distance
            for t in traces if component in t.distributions
        ]
        pull[component] = weights.of(component) * (
            sum(measured) / len(measured) if measured else 0.0
        )
    total = sum(pull.values())
    return {c: (v / total if total > 0 else 0.0) for c, v in pull.items()}


@dataclass(frozen=True)
class Search:
    """What the grid search found, and how much of it the data really decided."""

    weights: Weights
    best: Weights
    best_value: float
    chosen_value: float
    ranges: dict[str, tuple[float, float]]
    candidates: int
    accepted: int

    def undecided(self, component: str, span: float = 0.5) -> bool:
        """Whether this component's weight was essentially not chosen at all.

        True when the weights compatible with the backtest cover more than
        ``span`` of the whole range. The report says so next to the number,
        because "40%" and "40%, and anything from 0% to 85% would have done"
        are very different claims and only one of them is what happened here.
        """
        low, high = self.ranges.get(component, (0.0, 1.0))
        return high - low > span


def search(
    traces: list[Trace],
    components: tuple[str, ...],
    step: float = WEIGHT_STEP,
    sigmas: float = TOLERANCE_SIGMAS,
    min_influence: float = MIN_INFLUENCE,
) -> Search:
    """Grid search, then two corrections that stop it reporting noise as a fit.

    The search itself is the whole of the performance judgement: every
    weighting on the simplex is scored on the same stored distributions, no
    component has a floor or a prior, and the best one wins. What follows are
    not second opinions about performance. They are answers to "did the data
    actually choose this number?", and on a lottery archive the honest answer
    is usually no.

    **The first correction is why the ensemble is not simply a copy of one of
    its components.** With nothing to find, the objective over the grid is
    noise, and the minimum of noise over 231 candidates lands on a corner of
    the simplex about as often as anywhere else — a "fitted" weighting of
    100% frequenza, which is not an ensemble and is not a finding. So the
    accepted set is every weighting the backtest cannot distinguish from the
    best one (see :data:`TOLERANCE_SIGMAS`), and the one chosen out of it is
    the **most even** — the maximum-entropy point. Where there is something to
    find the accepted set is small and this changes nothing; where there is
    not, the weights stay as neutral as the evidence, instead of announcing a
    preference the evidence does not support. The report prints how wide the
    accepted set was for each component, so the difference is visible rather
    than inferred.

    **The second is :data:`MIN_INFLUENCE`**, which zeroes a weight that could
    not have been measured because the component is flat. That is the one
    that lets TimesFM reach exactly zero on this data, and it runs last so
    that the evenness above cannot put a weight back on a component that does
    not move the ranking.
    """
    if not traces:
        raise ValueError("nessuna estrazione su cui ottimizzare i pesi")
    usable = tuple(c for c in components if all(c in t.distributions for t in traces))
    if not usable:
        raise ValueError("nessun componente è stato misurato su tutte le estrazioni")
    prepared = _vectorise(traces, usable)
    n = len(traces)

    scored: list[tuple[Weights, list[float], float]] = []
    for candidate in weight_grid(usable, step):
        series = _rank_series(prepared, [candidate.of(c) for c in usable])
        scored.append((candidate, series, sum(series) / n))
    best, best_series, best_value = min(scored, key=lambda row: row[2])

    accepted = [
        (candidate, value) for candidate, series, value in scored
        if value - best_value <= sigmas * _paired_error(series, best_series)
    ]
    chosen, chosen_value = max(
        accepted, key=lambda row: (_evenness(row[0]), -row[1])
    )
    ranges = {
        c: (
            min(candidate.of(c) for candidate, _ in accepted),
            max(candidate.of(c) for candidate, _ in accepted),
        )
        for c in usable
    }
    return Search(
        weights=_drop_the_unmeasurable(
            chosen, _spreads(traces, usable), min_influence
        ),
        best=best,
        best_value=best_value,
        chosen_value=chosen_value,
        ranges=ranges,
        candidates=len(scored),
        accepted=len(accepted),
    )


def optimise(
    traces: list[Trace],
    components: tuple[str, ...],
    step: float = WEIGHT_STEP,
    min_influence: float = MIN_INFLUENCE,
) -> Weights:
    """Just the weights out of :func:`search`, for the callers that want only those."""
    return search(traces, components, step, min_influence=min_influence).weights


def _paired_error(series: list[float], reference: list[float]) -> float:
    """Standard error of the mean difference between two weightings' scores.

    Both were scored on the same draws, so this is a paired comparison and the
    draw-to-draw variation the two share cancels. Zero when the two produce
    the same ranking on every draw, which is the case that matters most: it
    makes them tied only if their means are equal too, so a component that
    changes nothing cannot be waved through on a wide error bar.
    """
    n = len(series)
    if n < 2:
        return 0.0
    differences = [a - b for a, b in zip(series, reference, strict=True)]
    mean = sum(differences) / n
    variance = sum((d - mean) ** 2 for d in differences) / (n - 1)
    return (variance / n) ** 0.5


def _evenness(weights: Weights) -> float:
    """The entropy of a weighting: highest when it spreads evenly.

    The tie-break over everything the backtest could not distinguish. It is
    deliberately *not* a prior on the weights — it never competes with the
    objective, it only decides between weightings the objective scored the
    same.
    """
    return -sum(w * math.log(w) for w in weights.values.values() if w > 0)


def _spreads(traces: list[Trace], components: tuple[str, ...]) -> dict[str, float]:
    """Each component's average distance from uniform over the backtest."""
    return {c: _mean_informativeness(traces, c).distance for c in components}


def _drop_the_unmeasurable(
    weights: Weights, spreads: dict[str, float], min_influence: float
) -> Weights:
    """Zero the weights that cannot have been measured, and renormalise.

    One pass, smallest influence first, stopping as soon as a component clears
    the bar — the shares only grow as others are removed, so anything already
    above it stays above it. The last component standing is never dropped: an
    empty weighting is not a result, it is a crash further down.

    Renormalising rather than re-running the search is deliberate and is
    exactly as good: what has been removed was, by the definition of the bar,
    not changing the order, so the search over what is left would come back
    with the same proportions and cost another 231 evaluations to do it.
    """
    current = dict(weights.values)
    while True:
        pull = {c: current[c] * spreads.get(c, 0.0) for c in current if current[c] > 0}
        total = sum(pull.values())
        if len(pull) <= 1 or total <= 0:
            break
        weakest = min(pull, key=lambda c: pull[c])
        if pull[weakest] / total >= min_influence:
            break
        current[weakest] = 0.0
        kept = sum(current.values())
        current = {c: (w / kept if kept > 0 else 0.0) for c, w in current.items()}
    return Weights(current)


def rolling(
    traces: list[Trace],
    components: tuple[str, ...],
    train: int,
    step: float = WEIGHT_STEP,
    refit_every: int = REFIT_EVERY,
) -> tuple[Performance, list[tuple[date, Weights]]]:
    """Walk the validation slice, refitting as a real run would.

    Target *t* is scored with weights fitted on targets strictly before *t*,
    refitted every ``refit_every`` draws. This is the procedure measured end
    to end rather than a weighting measured out of sample, and it is the only
    figure here that accounts for the weights themselves moving.
    """
    if train <= 0 or train >= len(traces):
        raise ValueError("il taglio fra addestramento e verifica è fuori dai dati")
    weights: list[Weights] = []
    updates: list[tuple[date, Weights]] = []
    current = optimise(traces[:train], components, step)
    updates.append((traces[train].draw_date, current))
    for offset in range(train, len(traces)):
        if offset > train and (offset - train) % refit_every == 0:
            current = optimise(traces[:offset], components, step)
            updates.append((traces[offset].draw_date, current))
        weights.append(current)
    return evaluate(traces[train:], weights, "ensemble (ricalibrato)"), updates


# ─────────────────────────────────────────────────────────────
# The fit
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EnsembleFit:
    """Everything the backtest decided, and everything it decided it from."""

    components: tuple[str, ...]
    weights: Weights
    train_weights: Weights
    window: int
    train_draws: int
    validation_draws: int
    first_target: date | None
    last_target: date | None
    archive_size: int
    archive_last_date: date | None
    train: dict[str, Performance] = field(default_factory=dict)
    validation: dict[str, Performance] = field(default_factory=dict)
    rolling: Performance | None = None
    updates: list[tuple[date, Weights]] = field(default_factory=list)
    informativeness: dict[str, Informativeness] = field(default_factory=dict)
    influence: dict[str, float] = field(default_factory=dict)
    # Per component, the lowest and highest weight the backtest could not tell
    # apart from the one chosen. A wide interval is the fit saying it did not
    # really decide, which on this data is the usual answer and has to be on
    # the page rather than in a docstring.
    ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    candidates: int = 0
    accepted: int = 0
    contributions: dict[str, float] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def measured_timesfm(self) -> bool:
        """Whether the model was actually in the backtest.

        A zero weight means two very different things and they must not be
        confused: "measured and worth nothing" is a result, "not measured"
        is a machine without the weights installed.
        """
        return "timesfm" in self.components

    def report_lines(self) -> list[str]:
        """This fit as text — :func:`report`, reachable from the object.

        The module-level function is the one that does the work; this exists
        because ``from core.ensemble import fit, report`` puts two very
        ordinary names into a caller's namespace and one of them is already
        taken in most of them.
        """
        return report(self)

    def as_record(self) -> dict:
        """The fit as JSON, for ``data/ensemble/weights.json``.

        The rendered report travels with it. The panel shows the evidence
        beside the weights on every run, including the runs that reuse a
        stored fit rather than recomputing one, and a stored weighting whose
        justification cannot be shown is the black box this is not.
        """
        return {
            "report": self.report_lines(),
            "components": list(self.components),
            "weights": self.weights.as_record(),
            "train_weights": self.train_weights.as_record(),
            "window": self.window,
            "train_draws": self.train_draws,
            "validation_draws": self.validation_draws,
            "first_target": self.first_target.isoformat() if self.first_target else None,
            "last_target": self.last_target.isoformat() if self.last_target else None,
            "archive_size": self.archive_size,
            "archive_last_date": (
                self.archive_last_date.isoformat() if self.archive_last_date else None
            ),
            "generated_at": self.generated_at.isoformat(),
            "contributions": {c: round(v, 4) for c, v in self.contributions.items()},
            "influence": {c: round(v, 4) for c, v in self.influence.items()},
            "ranges": {
                c: [round(low, 4), round(high, 4)]
                for c, (low, high) in self.ranges.items()
            },
            "validation_mean_rank": {
                label: round(p.mean_rank, 4) for label, p in self.validation.items()
            },
            "rolling_mean_rank": (
                round(self.rolling.mean_rank, 4) if self.rolling else None
            ),
        }


def _slices(
    draws: list[Draw], backtest_draws: int, validation_draws: int, min_history: int
) -> tuple[list[int], int]:
    """The target indices and where the train slice ends.

    Refuses rather than shrinking silently when the archive cannot support a
    split: a "backtest" of four draws that reports weights would be worse
    than no backtest, because it would look like one.
    """
    total = len(draws)
    start = max(min_history, total - backtest_draws)
    targets = list(range(start, total))
    train = len(targets) - validation_draws
    if len(targets) < 20 or train < 10 or validation_draws < 5:
        raise ValueError(
            f"{total} estrazioni non bastano per calibrare i pesi: servono almeno "
            f"{min_history} di storico più una ventina da valutare, di cui almeno "
            "cinque tenute da parte per la verifica"
        )
    return targets, train


def _mean_informativeness(traces: list[Trace], component: str) -> Informativeness:
    """One component's average informativeness over the backtest.

    Averaged rather than taken from the last draw: a component's spread moves
    from draw to draw — ``ritardo``'s especially, since one long-absent number
    dominates it until it comes out — and the weights were fitted over the
    whole run, so the diagnostic beside them has to describe the whole run too.
    """
    measured = [
        informativeness(t.distributions[component])
        for t in traces if component in t.distributions
    ]
    if not measured:
        return Informativeness(1.0, float(NUMBER_MAX), 0.0)
    n = len(measured)
    return Informativeness(
        entropy=sum(i.entropy for i in measured) / n,
        candidates=sum(i.candidates for i in measured) / n,
        distance=sum(i.distance for i in measured) / n,
    )


def fit(
    draws: list[Draw],
    window: int = DEFAULT_WINDOW,
    forecaster=None,
    backtest_draws: int = DEFAULT_BACKTEST_DRAWS,
    validation_draws: int = DEFAULT_VALIDATION_DRAWS,
    step: float = WEIGHT_STEP,
    seed: int = 0,
    min_history: int = MIN_HISTORY,
    cache: TraceCache | None = None,
    progress=None,
) -> EnsembleFit:
    """Run the backtest and come back with weights and the evidence for them.

    ``forecaster`` is what decides whether TimesFM is a component at all. With
    no model the fit is over two components and says so; the alternative — a
    third component of zeros, or of uniform noise — would put a number in the
    weights table that looked measured and was not.
    """
    components = tuple(c for c in COMPONENTS if c != "timesfm" or forecaster is not None)
    targets, train = _slices(draws, backtest_draws, validation_draws, min_history)
    traces = build_traces(
        draws, targets, components, window=window, forecaster=forecaster,
        seed=seed, cache=cache, progress=progress,
    )

    if progress:
        progress("Ricerca dei pesi…", 0.9)
    train_search = search(traces[:train], components, step)
    train_weights = train_search.weights
    found = search(traces, components, step)
    all_weights = found.weights

    def table(slice_: list[Trace], weights: Weights) -> dict[str, Performance]:
        found = {"ensemble": evaluate(slice_, weights, "ensemble")}
        for component in components:
            found[component] = evaluate(slice_, only(component), method_name(component))
        found[CONTROL] = evaluate(slice_, only(CONTROL), method_name(CONTROL))
        found["uniforme"] = evaluate(
            slice_, equal_weights(components), "pesi uguali",
        )
        return found

    validation = table(traces[train:], train_weights)
    train_table = table(traces[:train], train_weights)

    # What each component is worth *inside* the ensemble: refit without it on
    # the train slice, judge on the validation slice, and report the
    # difference. Positive means the ensemble is better with the component in
    # it. This is the number that answers "how much does TimesFM add?", and it
    # is allowed to come out zero or negative.
    contributions: dict[str, float] = {}
    for component in components:
        rest = tuple(c for c in components if c != component)
        if not rest:
            continue
        without = optimise(traces[:train], rest, step)
        performance = evaluate(traces[train:], without, f"senza {method_name(component)}")
        validation[f"senza {component}"] = performance
        contributions[component] = performance.mean_rank - validation["ensemble"].mean_rank

    rolled, updates = rolling(traces, components, train, step)

    means = {c: _mean_informativeness(traces, c) for c in components}
    shares = influence(traces, all_weights)

    if progress:
        progress("Pesi calibrati.", 1.0)
    return EnsembleFit(
        components=components,
        weights=all_weights,
        train_weights=train_weights,
        window=window,
        train_draws=train,
        validation_draws=len(traces) - train,
        first_target=traces[0].draw_date,
        last_target=traces[-1].draw_date,
        archive_size=len(draws),
        archive_last_date=draws[-1].date if draws else None,
        train=train_table,
        validation=validation,
        rolling=rolled,
        updates=updates,
        informativeness=means,
        influence=shares,
        ranges=found.ranges,
        candidates=found.candidates,
        accepted=found.accepted,
        contributions=contributions,
    )


# ─────────────────────────────────────────────────────────────
# Using the weights on the next draw
# ─────────────────────────────────────────────────────────────

def next_draw_scores(
    draws: list[Draw],
    weights: Weights,
    window: int = DEFAULT_WINDOW,
    forecaster=None,
    seed: int = 0,
    progress=None,
) -> tuple[dict[int, float], dict[str, dict[int, float]]]:
    """The ensemble's score for every number, and every component's own.

    Both are returned because the panel prints them side by side: a combined
    ranking whose parts cannot be inspected is the black box this is not
    supposed to be.

    Only components with a weight above zero are computed. A fit that put
    TimesFM at zero therefore costs no forward pass at all, which is the one
    place in Tyche where a measurement makes the program faster.
    """
    wanted = tuple(c for c in weights.values if weights.of(c) > 0)
    raw = component_scores(
        draws, wanted, window=window, forecaster=forecaster, seed=seed,
        progress=progress,
    )
    parts = {c: distribution(v) for c, v in raw.items()}
    return blend(raw, weights), parts


def next_draw_superstar(
    draws: list[Draw],
    weights: Weights,
    window: int = DEFAULT_WINDOW,
    forecaster=None,
    seed: int = 0,
    progress=None,
) -> int:
    """The SuperStar the ensemble plays: the same weights, the other drum."""
    wanted = tuple(c for c in weights.values if weights.of(c) > 0)
    raw = superstar_component_scores(
        draws, wanted, window=window, forecaster=forecaster, seed=seed,
        progress=progress,
    )
    return rank_numbers(blend(raw, weights))[0]


def table_lines(
    scores: dict[int, float],
    parts: dict[str, dict[int, float]],
    components: tuple[str, ...] = COMPONENTS,
    rows: int = 15,
) -> list[str]:
    """The per-number table: what each component said, and what came out of it.

    Printed for the top ``rows`` of the combined ranking and for the last
    three, which is what gives the numbers a scale — a column of values around
    1.1% means nothing until the bottom of the same column is on screen.
    """
    shown = [c for c in components if c in parts]
    header = (
        f"{'n':>4} " + " ".join(f"{method_name(c):>11}" for c in shown)
        + f" {'ensemble':>11} {'pos.':>5}"
    )
    lines = [header, "─" * len(header)]
    order = rank_numbers(scores)
    for position, n in enumerate(order[:rows], 1):
        cells = " ".join(f"{parts[c][n]:>11.6f}" for c in shown)
        lines.append(f"{n:>4} {cells} {scores[n]:>11.6f} {position:>5}")
    if len(order) > rows + 3:
        lines.append("  …")
        for position, n in enumerate(order[-3:], len(order) - 2):
            cells = " ".join(f"{parts[c][n]:>11.6f}" for c in shown)
            lines.append(f"{n:>4} {cells} {scores[n]:>11.6f} {position:>5}")
    return lines


def report(fit: EnsembleFit) -> list[str]:
    """The whole fit as text: the CLI prints it, the panel appends it.

    Everything a reader needs to disbelieve it: which draws, which weights,
    how they were chosen, what each component scored alone, what the ensemble
    scored, what it would have scored without each component, and what the
    random control scored beside all of them.
    """
    lines = [
        "═" * 62,
        "I pesi dell'ensemble, e da dove vengono",
        "",
        f"Backtest su {fit.train_draws + fit.validation_draws} estrazioni, "
        f"dal {fit.first_target} al {fit.last_target}.",
        f"  {fit.train_draws} per cercare i pesi, {fit.validation_draws} tenute da "
        "parte e mai viste durante la ricerca.",
        f"  Finestra della frequenza: {fit.window} estrazioni.",
        f"  Calibrati il {fit.generated_at.date()} su {fit.archive_size} estrazioni.",
        "",
        f"Pesi in uso:           {fit.weights.describe()}",
        f"Pesi verificati:       {fit.train_weights.describe()}",
        "  I primi sono ricalcolati su tutte le estrazioni del backtest, i secondi",
        "  solo sulla parte di addestramento: sono quelli le cui prestazioni qui",
        "  sotto sono davvero fuori campione.",
    ]
    if not fit.measured_timesfm:
        lines += [
            "",
            "TimesFM non era disponibile durante la calibrazione: non è un peso zero",
            "guadagnato sul campo, è un componente non misurato. Scarica i pesi e",
            "ricalibra per sapere quanto vale.",
        ]

    lines += [
        "",
        "Peso, quanto quel peso conta davvero, e quanto il componente distingue",
        "i novanta numeri:",
        "",
        f"  {'componente':<12} {'peso':>6} {'compatibili':>13} {'influenza':>10} "
        f"{'entropia':>9} {'candidati':>10} {'distanza':>9}",
    ]
    for component in fit.components:
        info = fit.informativeness[component]
        low, high = fit.ranges.get(component, (0.0, 1.0))
        lines.append(
            f"  {method_name(component):<12} {fit.weights.of(component):>6.0%} "
            f"{f'{low:.0%}–{high:.0%}':>13} "
            f"{fit.influence.get(component, 0.0):>10.0%} {info.entropy:>9.4f} "
            f"{info.candidates:>10.1f} {info.distance:>9.4f}"
        )
    lines += [
        f"  Su {fit.candidates} combinazioni di pesi provate, {fit.accepted} sono "
        "risultate indistinguibili dalla",
        "  migliore: la colonna «compatibili» è l'intervallo che coprono. Dove è "
        "larga, il backtest",
        "  non ha scelto quel peso — fra quelli che non sapeva distinguere è "
        "stato preso il più",
        "  equilibrato, per non spacciare per misura il minimo del rumore.",
    ]
    lines += [
        "  Entropia 1,0000 e 90,0 candidati sono la distribuzione uniforme: un",
        "  componente che non distingue nulla. Misura quanto un componente si",
        "  sbilancia, non quanto ha ragione — è il backtest che risponde a quello.",
        "  L'influenza è il peso moltiplicato per quanto quel componente si",
        "  discosta dall'uniforme: è la quota della graduatoria finale che viene",
        "  davvero da lui, e non coincide con il peso quando i tre si sbilanciano",
        "  in modo diverso.",
    ]
    zeroed = [c for c in fit.components if fit.weights.of(c) == 0]
    if zeroed:
        lines += [
            "  A peso zero: " + ", ".join(method_name(c) for c in zeroed)
            + ". La sua distribuzione è troppo vicina all'uniforme perché un peso",
            f"  cambi la graduatoria: sotto il {MIN_INFLUENCE:.0%} di influenza il "
            "peso non è una misura, è",
            "  il rumore della ricerca. Misurato, e non ha guadagnato niente. "
            "Nessun componente ha",
            "  un minimo garantito.",
        ]
    lines += [
        "",
        f"Sulle {fit.validation_draws} estrazioni di verifica:",
        "",
    ]
    for label in ("ensemble", *fit.components, CONTROL, "uniforme"):
        if label in fit.validation:
            lines.append("  " + fit.validation[label].summary())
    if fit.rolling:
        lines += [
            "  " + fit.rolling.summary(),
            "  L'ultima riga è la procedura intera: ogni estrazione valutata con i",
            f"  pesi calcolati solo sulle precedenti, ricalibrati ogni {REFIT_EVERY}. "
            "È il",
            "  numero da leggere se se ne legge uno solo.",
        ]

    if fit.contributions:
        lines += ["", "Quanto aggiunge ogni componente all'ensemble:", ""]
        for component, delta in fit.contributions.items():
            verdict = (
                "toglierlo peggiora" if delta > 0.05
                else "toglierlo migliora" if delta < -0.05
                else "non cambia niente"
            )
            lines.append(
                f"  {method_name(component):<12} {delta:>+7.2f} posizioni di rango "
                f"medio — {verdict}"
            )
        lines.append(
            "  Rifittando i pesi senza quel componente e valutando sulle stesse "
            "estrazioni."
        )

    lines += ["", *_verdict(fit)]
    return lines


def _verdict(fit: EnsembleFit) -> list[str]:
    """What the run showed, said plainly and without hedging in either direction."""
    ensemble = fit.validation.get("ensemble")
    if ensemble is None:
        return ["Nessuna verifica eseguita."]
    control = fit.validation.get(CONTROL)
    rolled = fit.rolling or ensemble
    beaten = [
        method_name(c) for c in fit.components
        if c in fit.validation and fit.validation[c].mean_rank < ensemble.mean_rank
    ]
    lines = [
        f"Il caso vale un rango medio di {MEAN_RANK:.1f} e un MRR di {NULL_MRR:.3f}.",
    ]
    if abs(rolled.rank_z) < 2:
        lines.append(
            f"L'ensemble segna {rolled.mean_rank:.2f} con z = {rolled.rank_z:+.2f}: "
            "indistinguibile dal caso, che è"
        )
        lines.append(
            "il risultato atteso. I pesi dicono quale combinazione ha fatto meno "
            "peggio su queste estrazioni,"
        )
        lines.append(
            "non quale sa qualcosa. Nessun criterio di scelta dei numeri cambia le "
            "probabilità della ruota."
        )
    else:
        lines.append(
            f"L'ensemble segna {rolled.mean_rank:.2f} con z = {rolled.rank_z:+.2f} "
            f"(p = {rolled.rank_p:.3f}) sulle estrazioni di verifica."
        )
        lines.append(
            f"Con una ricerca su {len(weight_grid(fit.components))} combinazioni di "
            "pesi, uno scarto del genere capita anche senza che ci sia niente:"
        )
        lines.append(
            "rifai la calibrazione su un'altra porzione dell'archivio prima di "
            "considerarlo un risultato."
        )
    if control is not None:
        lines.append(
            f"Il controllo casuale, sulle stesse estrazioni, segna "
            f"{control.mean_rank:.2f} con z = {control.rank_z:+.2f}."
        )
    if beaten:
        lines.append(
            "Su questa verifica l'ensemble non batte: " + ", ".join(beaten)
            + ". Un ensemble che non migliora le sue componenti è una componente in più, "
            "non un metodo migliore."
        )
    return lines


# ─────────────────────────────────────────────────────────────
# Reusing a fit across sessions
# ─────────────────────────────────────────────────────────────

def weights_from_record(record: dict | None) -> Weights | None:
    """The weights out of a stored fit, or None if there is nothing usable.

    Tolerant on purpose: the file lives in ``data/``, a user may have edited
    it, and a weighting that does not add up must produce "no stored fit"
    rather than an exception in the middle of a forecast.
    """
    if not isinstance(record, dict):
        return None
    values = record.get("weights")
    if not isinstance(values, dict) or not values:
        return None
    try:
        numbers = {str(c): float(w) for c, w in values.items()}
        total = sum(numbers.values())
        if total <= 0:
            return None
        return Weights({c: w / total for c, w in numbers.items()})
    except (TypeError, ValueError):
        return None


def is_current(
    record: dict | None,
    draws: list[Draw],
    window: int,
    with_timesfm: bool,
    refit_after: int = REFIT_AFTER,
) -> bool:
    """Whether a stored fit can still be used for the archive as it now is.

    Four ways it cannot, and each of them would otherwise be a weighting
    quietly applied to something it was not fitted for:

    - the archive has moved on by more than ``refit_after`` draws, or has
      moved *backwards*, which means it was re-imported rather than extended;
    - the frequency window changed, so one of the components is not the
      component that was measured;
    - TimesFM has become available since, so a component that was never
      measured could now be measured;
    - TimesFM has gone away, so a weight is being carried for a component
      that cannot answer.

    Age alone is not on that list. Weights fitted three weeks ago on the same
    archive are the same weights; it is the *evidence* moving that dates them.
    """
    if weights_from_record(record) is None:
        return False
    if record.get("window") != window:
        return False
    if ("timesfm" in (record.get("components") or [])) != with_timesfm:
        return False
    grown = len(draws) - int(record.get("archive_size", -1))
    return 0 <= grown <= refit_after


def cache_for(
    path: Path | None,
    window: int,
    checkpoint: str = "",
    context_length: int = 0,
) -> TraceCache:
    """A :class:`TraceCache` whose fingerprint covers what changes an answer.

    Everything TimesFM's forecast depends on except the history itself, which
    the per-entry key carries. A user who points Tyche at another checkpoint
    gets an empty cache rather than the old model's opinions under the new
    model's name.
    """
    return TraceCache(path, {
        "window": window,
        "checkpoint": checkpoint,
        "context_length": context_length,
    })
