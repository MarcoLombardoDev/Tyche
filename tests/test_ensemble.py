# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
tests/test_ensemble.py — Tyche

The combined method, and the two questions it has to keep answering:

- **does it cheat?** The backtest must never see the draw it is predicting,
  and the weights must never be fitted on the draws they are judged on.
  ``test_a_trace_cannot_see_past_its_own_target`` and
  ``test_the_weights_are_older_than_the_draws_they_are_judged_on`` are the
  ones to keep.
- **does a component have to earn its weight?** A component that adds nothing
  must be able to reach exactly zero, and one with a real edge must take the
  weight. Both directions are tested with forecasters built to have the
  property being looked for, because a test that only checks the no-signal
  case passes with the whole search deleted.

Everything here runs without torch, timesfm or a display. The model is stood
in for by two fakes: one that is flat, which is what TimesFM really does on
this data, and :class:`core.power._KnownEdge`, which cheats by a measured
amount and is the harness's own instrument.
"""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ensemble as E  # noqa: E402
from core.archive import ALL_NUMBERS, NUMBER_MAX, Draw  # noqa: E402
from core.scoring import MEAN_RANK  # noqa: E402

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def archive(n: int, seed: int = 0) -> list[Draw]:
    """Independent uniform draws, with a SuperStar from its own drum."""
    rng = random.Random(seed)
    draws = []
    start = date(2000, 1, 1)
    for i in range(n):
        picked = rng.sample(range(1, NUMBER_MAX + 1), 8)
        draws.append(Draw(
            date=start + timedelta(days=3 * i), contest=i + 1,
            numbers=tuple(picked[:6]), jolly=picked[6], superstar=picked[7],
            year=2000,
        ))
    return draws


class FlatModel:
    """A forecaster that says almost the same thing about every number.

    What TimesFM actually does on the raw presence series — see CLAUDE.md —
    and therefore the case the weighting has to get right. The jitter is
    deliberately not zero: exact ties would be caught by the tie-break rather
    than by the rule under test.
    """

    def score_numbers(self, history, progress=None):
        rng = random.Random(len(history))
        return {n: 0.0667 + rng.gauss(0, 0.0002) for n in ALL_NUMBERS}

    def score_superstar(self, history, progress=None):
        rng = random.Random(9000 + len(history))
        return {n: 0.0111 + rng.gauss(0, 0.0001) for n in ALL_NUMBERS}


def traces_for(draws, components=("ritardo", "frequenza"), count=40, forecaster=None):
    targets = list(range(len(draws) - count, len(draws)))
    return E.build_traces(draws, targets, components, forecaster=forecaster)


# ─────────────────────────────────────────────────────────────
# Putting three quantities on one scale
# ─────────────────────────────────────────────────────────────

def test_a_component_becomes_a_distribution():
    scores = {n: float(n) for n in ALL_NUMBERS}
    dist = E.distribution(scores)
    assert all(p >= 0 for p in dist.values())
    assert sum(dist.values()) == pytest.approx(1.0)


def test_a_negative_score_still_produces_a_distribution():
    """TimesFM can forecast one. The other two cannot, and nothing may assume so."""
    scores = {n: (n - 50) / 100 for n in ALL_NUMBERS}
    dist = E.distribution(scores)
    assert min(dist.values()) >= 0
    assert sum(dist.values()) == pytest.approx(1.0)


def test_a_flat_component_stays_flat():
    """The rule that stops the ensemble being rigged in TimesFM's favour.

    A min-max stretch, or a softmax with a temperature, would turn a fourth
    decimal into a confident-looking ranking — and the temperature, not the
    model, would be doing the ranking. Checked by mutation: normalising with
    ``(s - min) / (max - min)`` makes this fail on the first assertion.
    """
    scores = {n: 0.0667 + (n % 3) * 1e-6 for n in ALL_NUMBERS}
    dist = E.distribution(scores)
    assert max(dist.values()) - min(dist.values()) < 1e-6
    assert E.informativeness(dist).entropy > 0.9999
    assert E.informativeness(dist).candidates > 89.9


def test_a_score_with_no_spread_at_all_comes_back_uniform():
    dist = E.distribution(dict.fromkeys(ALL_NUMBERS, 0.0))
    assert dist == dict.fromkeys(ALL_NUMBERS, 1 / NUMBER_MAX)


def test_informativeness_separates_flat_from_concentrated():
    flat = dict.fromkeys(ALL_NUMBERS, 1 / NUMBER_MAX)
    sharp = E.distribution({n: 1.0 if n <= 9 else 0.0 for n in ALL_NUMBERS})
    assert E.informativeness(flat).entropy == pytest.approx(1.0)
    assert E.informativeness(flat).candidates == pytest.approx(NUMBER_MAX)
    assert E.informativeness(flat).distance == pytest.approx(0.0)
    assert E.informativeness(sharp).entropy < 0.6
    assert E.informativeness(sharp).candidates == pytest.approx(9, abs=0.01)
    assert E.informativeness(sharp).distance > 0.8


# ─────────────────────────────────────────────────────────────
# Weights
# ─────────────────────────────────────────────────────────────

def test_weights_must_be_non_negative_and_sum_to_one():
    E.Weights({"a": 0.25, "b": 0.75})
    with pytest.raises(ValueError, match="negativo"):
        E.Weights({"a": -0.5, "b": 1.5})
    with pytest.raises(ValueError, match="sommare"):
        E.Weights({"a": 0.25, "b": 0.25})


def test_the_grid_covers_the_simplex_and_nothing_else():
    grid = E.weight_grid(("a", "b", "c"), 0.05)
    # C(n + k - 1, k - 1) with n = 20 steps and k = 3 components.
    assert len(grid) == math.comb(22, 2)
    for candidate in grid:
        assert sum(candidate.values.values()) == pytest.approx(1.0)
        assert all(w >= 0 for w in candidate.values.values())
    corners = [c for c in grid if len(c.used) == 1]
    assert len(corners) == 3, "every single-component weighting must be reachable"


def test_the_grid_is_in_a_fixed_order():
    """Two runs must return the same weights, so ties cannot be resolved by luck."""
    assert [c.values for c in E.weight_grid(("a", "b"), 0.1)] == [
        c.values for c in E.weight_grid(("a", "b"), 0.1)
    ]


# ─────────────────────────────────────────────────────────────
# No look-ahead — the two that matter most
# ─────────────────────────────────────────────────────────────

def test_a_trace_cannot_see_past_its_own_target():
    """The strongest form of the check: delete the future and nothing moves.

    If any component read ``draws[i]`` or later, truncating the archive right
    after the last target would change what it produced. Nothing here does,
    so the two runs are identical dictionary for dictionary.
    """
    draws = archive(360)
    targets = list(range(300, 320))
    whole = E.build_traces(draws, targets, ("ritardo", "frequenza"))
    cut = E.build_traces(draws[:320], targets, ("ritardo", "frequenza"))
    assert [t.distributions for t in whole] == [t.distributions for t in cut]
    assert [t.actual for t in whole] == [t.actual for t in cut]


def test_the_target_is_never_in_the_history_it_is_scored_against():
    draws = archive(320)
    traces = E.build_traces(draws, [310, 311], ("ritardo",))
    for trace in traces:
        assert trace.history_size == trace.index
        # The gap component would report a gap of zero for a number drawn in
        # the target itself. core/features writes the reset at t+1 for exactly
        # this reason, and this is the assertion that would catch it moving.
        gaps = E.component_scores(draws[:trace.index], ("ritardo",))["ritardo"]
        assert trace.distributions["ritardo"] == E.distribution(gaps)


def test_the_weights_are_older_than_the_draws_they_are_judged_on():
    """The walk-forward refit: every target scored with weights fitted before it.

    Checked by construction rather than by inspection — the weights for the
    first validation target are recomputed here from the training traces
    alone, and they have to be the ones ``rolling`` used.
    """
    draws = archive(300)
    traces = traces_for(draws, count=40)
    performance, updates = E.rolling(
        traces, ("ritardo", "frequenza"), train=25, step=0.25, refit_every=5,
    )
    assert performance.draws_scored == 15
    assert updates, "the rolling check never fitted anything"
    first_date, first_weights = updates[0]
    assert first_date == traces[25].draw_date
    assert first_weights.values == E.optimise(
        traces[:25], ("ritardo", "frequenza"), 0.25
    ).values
    # And it really refits as it goes rather than once at the start.
    assert len(updates) == 3


def test_a_fit_never_scores_a_weighting_on_the_draws_that_chose_it():
    draws = archive(300)
    fit = E.fit(
        draws, backtest_draws=60, validation_draws=20, min_history=60, step=0.25,
    )
    assert fit.train_draws == 40
    assert fit.validation_draws == 20
    assert fit.validation["ensemble"].draws_scored == 20
    assert fit.train["ensemble"].draws_scored == 40


# ─────────────────────────────────────────────────────────────
# The objective
# ─────────────────────────────────────────────────────────────

def test_the_fast_objective_is_the_slow_one():
    """The search and the report must optimise and print the same number.

    :func:`core.ensemble._rank_series` exists only because the grid evaluates
    every candidate over every trace; if it ever stopped agreeing with
    :func:`core.ensemble.evaluate`, the panel would be printing the score of a
    weighting chosen on a different one.
    """
    draws = archive(280)
    traces = traces_for(draws, count=30)
    prepared = E._vectorise(traces, ("ritardo", "frequenza"))
    weights = E.Weights({"ritardo": 0.35, "frequenza": 0.65})
    fast = sum(E._rank_series(prepared, [0.35, 0.65])) / len(traces)
    assert fast == pytest.approx(E.evaluate(traces, weights).mean_rank, abs=1e-9)


def test_the_metrics_are_reported_at_every_requested_depth():
    draws = archive(280)
    traces = traces_for(draws, count=30)
    performance = E.evaluate(traces, E.equal_weights(("ritardo", "frequenza")))
    for k in (5, 6, 10, 15, 20, 30):
        assert k in performance.hits_at
        assert 0 <= performance.rate_at[k] <= 1
        assert performance.expected_hits_at[k] == pytest.approx(
            len(traces) * 6 * k / 90
        )
    assert 0 < performance.mrr <= 1
    assert 1 <= performance.mean_rank <= NUMBER_MAX


def test_chance_is_computed_and_not_quoted():
    """The null MRR is exact combinatorics, so it can be checked against one."""
    total = math.comb(90, 6)
    by_hand = sum(
        math.comb(90 - m, 5) / total / m for m in range(1, 86)
    )
    assert pytest.approx(by_hand) == E.NULL_MRR
    assert pytest.approx(0.198, abs=0.005) == E.NULL_MRR


def test_an_uninformative_ensemble_scores_chance():
    """Sanity on the harness itself: uniform scores give the null mean rank."""
    draws = archive(280)
    traces = traces_for(draws, count=30)
    flat = [
        E.Trace(
            index=t.index, draw_id=t.draw_id, draw_date=t.draw_date,
            history_size=t.history_size, actual=t.actual,
            distributions={"ritardo": dict.fromkeys(ALL_NUMBERS, 1 / NUMBER_MAX)},
        )
        for t in traces
    ]
    performance = E.evaluate(flat, E.only("ritardo"))
    assert performance.mean_rank == pytest.approx(MEAN_RANK)
    assert performance.rank_z == 0.0, "a method with no spread cannot beat chance"


# ─────────────────────────────────────────────────────────────
# Earning the weight, in both directions
# ─────────────────────────────────────────────────────────────

def test_a_flat_component_gets_no_weight_at_all():
    """TimesFM on this data, and the point of the whole exercise.

    Its forecast is the same to four decimals for all ninety numbers, so any
    weight on it leaves the ranking where it was and the backtest cannot
    measure one. Checked by mutation: with ``min_influence=0`` the search
    happily hands it 55%, which is what the first version of this module
    printed.
    """
    draws = archive(300)
    traces = traces_for(
        draws, ("timesfm", "ritardo", "frequenza"), count=50, forecaster=FlatModel(),
    )
    weights = E.optimise(traces, ("timesfm", "ritardo", "frequenza"), 0.05)
    assert weights.of("timesfm") == 0.0
    assert sum(weights.values.values()) == pytest.approx(1.0)

    unguarded = E.search(
        traces, ("timesfm", "ritardo", "frequenza"), 0.05, min_influence=0.0,
    ).weights
    assert unguarded.of("timesfm") > 0.0, (
        "the guard is doing nothing — the search did not want a weight there anyway"
    )


def test_a_component_with_a_real_edge_takes_the_weight():
    """The other direction, without which the test above passes with w = 0 forced.

    ``_KnownEdge`` reads the draw it is predicting and leaks part of it, so it
    has a genuine, measured advantage. Nothing in the fit knows that; it has
    to find it in the backtest.
    """
    from core.power import _KnownEdge

    draws = archive(300, seed=5)
    fit = E.fit(
        draws, backtest_draws=80, validation_draws=30, min_history=60, step=0.1,
        forecaster=_KnownEdge(draws, "diffuso", 0.30),
    )
    assert fit.weights.of("timesfm") > 0.5, fit.weights.describe()
    assert fit.contributions["timesfm"] > 1.0, (
        "removing a component with a real edge has to cost the ensemble"
    )
    assert fit.validation["ensemble"].mean_rank < fit.validation["frequenza"].mean_rank
    assert fit.rolling.rank_z > 3


def test_the_rule_is_not_about_timesfm_in_particular():
    """Any component that stops distinguishing loses its weight, not just the model.

    Built by replacing one component's distribution with the uniform one, in
    each position in turn. A rule that only knew how to zero ``timesfm``
    would pass the test above and fail this one.
    """
    draws = archive(300)
    traces = traces_for(draws, ("ritardo", "frequenza"), count=50)
    flat = dict.fromkeys(ALL_NUMBERS, 1 / NUMBER_MAX)
    for blind in ("ritardo", "frequenza"):
        blinded = [
            E.Trace(
                index=t.index, draw_id=t.draw_id, draw_date=t.draw_date,
                history_size=t.history_size, actual=t.actual,
                distributions={
                    c: (flat if c == blind else d)
                    for c, d in t.distributions.items()
                },
            )
            for t in traces
        ]
        weights = E.optimise(blinded, ("ritardo", "frequenza"), 0.05)
        assert weights.of(blind) == 0.0, f"{blind}: {weights.describe()}"
        assert sum(weights.values.values()) == pytest.approx(1.0)


def test_removing_a_component_really_produces_a_different_ensemble():
    """Not a tautology: the blend has to actually drop it and renormalise."""
    draws = archive(260)
    scores = E.component_scores(draws, ("ritardo", "frequenza"))
    both = E.blend(scores, E.Weights({"ritardo": 0.5, "frequenza": 0.5}))
    one = E.blend(scores, E.Weights({"ritardo": 1.0, "frequenza": 0.0}))
    assert both != one
    assert sum(both.values()) == pytest.approx(1.0)
    assert sum(one.values()) == pytest.approx(1.0)
    assert one == E.distribution(scores["ritardo"])


def test_a_missing_component_is_dropped_and_the_rest_renormalised():
    """A machine with no model must still get an ensemble, not a broken one."""
    draws = archive(260)
    scores = E.component_scores(draws, ("ritardo", "frequenza"))
    weights = E.Weights({"timesfm": 0.5, "ritardo": 0.25, "frequenza": 0.25})
    blended = E.blend(scores, weights)
    assert sum(blended.values()) == pytest.approx(1.0)
    assert E.missing(scores, weights) == ("timesfm",)
    assert blended == pytest.approx(
        E.blend(scores, E.Weights({"ritardo": 0.5, "frequenza": 0.5}))
    )


def test_the_search_says_how_much_of_the_weighting_it_actually_decided():
    """On a fair archive it decides nothing, and has to be able to say so."""
    draws = archive(300, seed=11)
    traces = traces_for(draws, count=60)
    found = E.search(traces, ("ritardo", "frequenza"), 0.05)
    assert found.candidates == 21
    assert found.accepted >= 1
    low, high = found.ranges["ritardo"]
    assert low <= found.weights.of("ritardo") <= high
    if found.accepted == found.candidates:
        assert found.undecided("ritardo"), (
            "every weighting was compatible and the report would still claim a choice"
        )


def test_the_weights_do_not_collapse_onto_one_component_on_a_fair_archive():
    """The defect the evenness tie-break exists for.

    With nothing to find, the minimum of the objective over 231 candidates
    lands on a corner of the simplex as readily as anywhere — and a corner is
    not an ensemble, it is one of the other cells copied into the first one.
    Among the weightings the backtest could not tell apart, the most even one
    is taken instead.

    Made deterministic by giving the fit two components that are *the same
    component*: every weighting then produces exactly the same ranking, every
    one of them is tied, and the only defensible answer is the middle. Taking
    the best-scoring one instead returns the first corner the grid reaches —
    checked by mutation, and that is what it did.
    """
    draws = archive(300)
    traces = traces_for(draws, count=50)
    twinned = [
        E.Trace(
            index=t.index, draw_id=t.draw_id, draw_date=t.draw_date,
            history_size=t.history_size, actual=t.actual,
            distributions={
                "ritardo": t.distributions["ritardo"],
                "frequenza": t.distributions["ritardo"],
            },
        )
        for t in traces
    ]
    weights = E.optimise(twinned, ("ritardo", "frequenza"), 0.05)
    assert weights.values == {"ritardo": 0.5, "frequenza": 0.5}, weights.describe()

    # And on a real fair archive it stays a mixture rather than a copy.
    for seed in (1, 2, 3, 4, 5):
        traces = traces_for(archive(320, seed=seed), count=60)
        mixed = E.optimise(traces, ("ritardo", "frequenza"), 0.05)
        assert len(mixed.used) == 2, f"seed {seed}: collapsed to {mixed.describe()}"


# ─────────────────────────────────────────────────────────────
# The control
# ─────────────────────────────────────────────────────────────

def test_the_random_control_is_measured_and_can_never_be_a_component():
    """Same guard as the Prediction panel's random cell, one level down."""
    assert E.CONTROL not in E.COMPONENTS
    grid = E.weight_grid(E.COMPONENTS, 0.25)
    assert all(E.CONTROL not in candidate.values for candidate in grid)

    draws = archive(300)
    fit = E.fit(
        draws, backtest_draws=60, validation_draws=20, min_history=60, step=0.25,
    )
    assert E.CONTROL in fit.validation, "the control has to be on the table"
    assert E.CONTROL not in fit.weights.values


def test_the_report_shows_every_baseline_and_says_what_the_run_meant():
    draws = archive(300)
    fit = E.fit(
        draws, backtest_draws=60, validation_draws=20, min_history=60, step=0.25,
    )
    text = "\n".join(E.report(fit))
    for expected in ("Ritardo", "Frequenza", "Casuale", "ensemble", "verifica"):
        assert expected in text
    assert "indistinguibile dal caso" in text, (
        "a fair archive has to be reported as one"
    )
    assert str(fit.validation_draws) in text


def test_an_archive_too_short_to_split_is_refused_rather_than_split_anyway():
    with pytest.raises(ValueError, match="non bastano"):
        E.fit(archive(210), backtest_draws=120, validation_draws=40)


# ─────────────────────────────────────────────────────────────
# Reuse across sessions
# ─────────────────────────────────────────────────────────────

def test_a_fit_round_trips_through_its_record():
    draws = archive(300)
    fit = E.fit(
        draws, backtest_draws=60, validation_draws=20, min_history=60, step=0.25,
    )
    record = json.loads(json.dumps(fit.as_record(), default=str))
    assert E.weights_from_record(record).values == fit.weights.values
    assert record["report"], "the evidence has to travel with the weights"


def test_a_stored_fit_is_refused_when_it_no_longer_describes_the_archive():
    draws = archive(300)
    record = {
        "weights": {"ritardo": 0.5, "frequenza": 0.5},
        "components": ["ritardo", "frequenza"],
        "window": 208,
        "archive_size": len(draws),
    }
    assert E.is_current(record, draws, 208, with_timesfm=False)
    # A few new draws are fine; a re-imported archive is not.
    assert E.is_current(record, draws + archive(3, seed=9), 208, with_timesfm=False)
    assert not E.is_current(record, draws + archive(40, seed=9), 208, False)
    assert not E.is_current(record, draws[:-5], 208, with_timesfm=False)
    # A different window is a different component.
    assert not E.is_current(record, draws, 150, with_timesfm=False)
    # The model arriving is a reason to measure it.
    assert not E.is_current(record, draws, 208, with_timesfm=True)


def test_a_broken_or_missing_record_is_simply_no_weights():
    assert E.weights_from_record(None) is None
    assert E.weights_from_record({}) is None
    assert E.weights_from_record({"weights": {}}) is None
    assert E.weights_from_record({"weights": {"a": "x"}}) is None
    assert E.weights_from_record({"weights": {"a": 0.0}}) is None
    # A weighting that does not add up is renormalised rather than refused:
    # it is still an ordering, and the file is one a user can edit.
    assert E.weights_from_record({"weights": {"a": 1, "b": 3}}).of("b") == 0.75


def test_the_trace_cache_only_keeps_what_is_expensive(tmp_path):
    """Caching the cheap components would be a way to be wrong for no saving."""
    path = tmp_path / "traces.json"
    cache = E.cache_for(path, 208, "org/model", 1024)
    cache.put("timesfm", "2020/1", 100, dict.fromkeys(ALL_NUMBERS, 0.5))
    cache.put("ritardo", "2020/1", 100, dict.fromkeys(ALL_NUMBERS, 0.5))
    cache.save()

    again = E.cache_for(path, 208, "org/model", 1024)
    assert again.get("timesfm", "2020/1", 100) is not None
    assert again.get("ritardo", "2020/1", 100) is None
    # A different history under the same draw id is a different question.
    assert again.get("timesfm", "2020/1", 101) is None


def test_the_trace_cache_is_emptied_when_the_model_changes(tmp_path):
    path = tmp_path / "traces.json"
    cache = E.cache_for(path, 208, "org/model", 1024)
    cache.put("timesfm", "2020/1", 100, dict.fromkeys(ALL_NUMBERS, 0.5))
    cache.save()
    assert E.cache_for(path, 208, "org/other", 1024).get("timesfm", "2020/1", 100) is None
    assert E.cache_for(path, 150, "org/model", 1024).get("timesfm", "2020/1", 100) is None


def test_the_cache_makes_the_second_fit_free_of_forward_passes(tmp_path):
    """The whole reason a refit after four new draws is not another hour."""
    class Counting(FlatModel):
        calls = 0

        def score_numbers(self, history, progress=None):
            type(self).calls += 1
            return super().score_numbers(history, progress)

    draws = archive(300)
    model = Counting()
    targets = list(range(260, 280))
    cache = E.cache_for(tmp_path / "traces.json", 208, "org/model", 1024)
    E.build_traces(draws, targets, ("timesfm",), forecaster=model, cache=cache)
    assert Counting.calls == 20

    warm = E.cache_for(tmp_path / "traces.json", 208, "org/model", 1024)
    E.build_traces(draws, targets, ("timesfm",), forecaster=model, cache=warm)
    assert Counting.calls == 20, "the second run paid for the model again"
    assert warm.hits == 20


# ─────────────────────────────────────────────────────────────
# The method, as the rest of the program sees it
# ─────────────────────────────────────────────────────────────

def test_the_ensemble_is_the_first_method_offered():
    from core.predictor import METHODS

    assert METHODS[0] == E.ENSEMBLE
    assert METHODS.index("ensemble") < METHODS.index("timesfm")


def test_predicting_without_weights_is_refused_rather_than_guessed():
    from core.predictor import predict

    with pytest.raises(ValueError, match="pesi calibrati"):
        predict(archive(300), method="ensemble")


def test_a_prediction_carries_its_weights_and_its_components():
    from core.predictor import predict

    draws = archive(300)
    weights = E.Weights({"ritardo": 0.4, "frequenza": 0.6})
    prediction = predict(draws, method="ensemble", combinations=1, weights=weights)
    assert len(prediction.combinations[0]) == 6
    assert prediction.detail["weights"] == {"ritardo": 0.4, "frequenza": 0.6}
    assert set(prediction.detail["components"]) == {"ritardo", "frequenza"}
    assert sum(prediction.scores.values()) == pytest.approx(1.0)
    # And the log can reproduce it, which a set of numbers alone cannot.
    assert prediction.to_log_entry()["weights"] == {"ritardo": 0.4, "frequenza": 0.6}


def test_the_ensemble_plays_a_superstar_from_the_superstar_drum():
    from core.predictor import predict, superstar_scores

    draws = archive(300)
    weights = E.Weights({"frequenza": 1.0})
    prediction = predict(
        draws, method="ensemble", combinations=1, weights=weights, superstar=True,
    )
    assert 1 <= prediction.superstar <= 90
    # Weighted entirely on frequency, so it must be that drum's own count and
    # not the wheel's — a number can be cold on one and hot on the other.
    from core.predictor import rank_numbers

    assert prediction.superstar == rank_numbers(superstar_scores(draws))[0]


def test_a_component_with_no_weight_is_never_asked_anything():
    """A zero weight on TimesFM has to save the forward pass, not just the mass."""
    class Refusing(FlatModel):
        def score_numbers(self, history, progress=None):
            raise AssertionError("the model was asked for a forecast it must not give")

    draws = archive(300)
    scores, parts = E.next_draw_scores(
        draws, E.Weights({"timesfm": 0.0, "ritardo": 0.5, "frequenza": 0.5}),
        forecaster=Refusing(),
    )
    assert set(parts) == {"ritardo", "frequenza"}
    assert sum(scores.values()) == pytest.approx(1.0)


def test_the_other_harness_refuses_the_ensemble_instead_of_scoring_it_as_chance():
    """core.validation._scores falls through to the random baseline for anything
    it does not know, so an unguarded ensemble would be reported as noise under
    its own name."""
    from core.validation import walk_forward

    with pytest.raises(ValueError, match="backtest"):
        walk_forward(archive(300), methods=["ensemble"], n_draws=20)


def test_the_table_shows_every_component_beside_the_combined_score():
    draws = archive(300)
    weights = E.Weights({"ritardo": 0.5, "frequenza": 0.5})
    scores, parts = E.next_draw_scores(draws, weights)
    lines = E.table_lines(scores, parts, ("ritardo", "frequenza"), rows=10)
    assert "Ritardo" in lines[0] and "Frequenza" in lines[0]
    assert "ensemble" in lines[0]
    # One row per requested position, plus the header, the rule, the ellipsis
    # and the three at the bottom that give the numbers a scale.
    assert len(lines) == 10 + 2 + 1 + 3
