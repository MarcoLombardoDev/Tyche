# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
validation.py — Tyche

Walk-forward backtesting: the module that decides whether anything else in
this program is worth running.

The procedure is the only honest one available. Step through the most recent
*N* draws; at each step show a method **only the draws before it**, take the
six numbers it ranks highest, and count how many of them came out. Sum over
the run and compare against what the same procedure would score by chance.

The chance figure is not a simulation, it is a closed form. Picking six of
ninety when six will be drawn gives a hypergeometric number of hits with mean
6 × 6 / 90 = **0.4 per draw** and variance 0.3524, so a 300-draw run has an
expected 120 hits with a standard error of about 10.3. A method needs to beat
that by 20 hits to reach two standard errors, and there is no reason any of
them should.

Two things this harness is careful about, because both are standard ways a
backtest of this shape reports skill that is not there:

- **No look-ahead.** ``draws[:i]`` and never ``draws[:i+1]``. The gap features
  in :mod:`core.features` are built the same way, with the reset applied at
  ``t+1``, so a number drawn at the target draw does not show a zero gap in
  the context that predicts it.
- **No selection after the fact.** Every method configured is scored over the
  same draws and all of them are reported. Running four and printing the best
  one is how a 5% test becomes a 19% one; the report shows the whole table.

Running the TimesFM method here costs one model forward pass per draw. On a
CPU that is minutes for a few hundred draws, which is why the baselines exist
and why they are worth running first: if ``random`` and ``frequency`` and
``gap`` all land on 0.4, the interesting question is not whether TimesFM will
too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.archive import NUMBER_MAX, NUMBERS_PER_DRAW, Draw
from core.features import DEFAULT_WINDOW
from core.predictor import METHODS, frequency_scores, gap_scores, random_scores, rank_numbers
from core.stats_tests import (
    chi_square_goodness_of_fit,
    hypergeom_moments,
    hypergeom_pmf,
    two_sided_normal_p,
)

# A method must have seen at least this many draws before it is asked for a
# prediction, so the earliest targets are not scored against a method that had
# forty draws of history while the later ones had three thousand.
MIN_HISTORY = 200


@dataclass(frozen=True)
class MethodResult:
    """One method's score over the whole walk-forward run."""

    method: str
    draws_scored: int
    picks_per_draw: int
    total_hits: int
    histogram: list[int]
    expected_mean: float
    expected_sd: float
    z: float
    p_value: float
    chi2: float
    chi2_dof: int
    chi2_p: float
    best_draw_hits: int
    three_or_more: int
    expected_three_or_more: float

    @property
    def mean_hits(self) -> float:
        return self.total_hits / self.draws_scored if self.draws_scored else 0.0

    @property
    def excess(self) -> float:
        """Hits above or below chance, in whole hits over the whole run."""
        return self.total_hits - self.expected_mean * self.draws_scored

    def summary(self) -> str:
        return (
            f"{self.method:<10} {self.mean_hits:.4f} centri/estrazione "
            f"(caso {self.expected_mean:.4f}), {self.total_hits} in totale, "
            f"{self.excess:+.1f} rispetto al caso, z = {self.z:+.2f}, "
            f"p = {self.p_value:.3f}"
        )


@dataclass(frozen=True)
class ValidationReport:
    """Every method's result over one run, plus the run's own parameters."""

    results: list[MethodResult]
    draws_scored: int
    first_target: Draw | None
    last_target: Draw | None
    picks_per_draw: int
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def best(self) -> MethodResult | None:
        return max(self.results, key=lambda r: r.total_hits) if self.results else None

    def verdict(self) -> str:
        """The paragraph the validation panel prints. Says what the run showed."""
        if not self.results:
            return "Nessun metodo valutato."
        beat = [r for r in self.results if r.p_value < 0.05 and r.z > 0]
        best = self.best()
        head = (
            f"{len(self.results)} metodi valutati su {self.draws_scored} estrazioni, "
            f"sei numeri ciascuno. Il caso vale "
            f"{self.results[0].expected_mean:.3f} centri per estrazione."
        )
        if not beat:
            return (
                f"{head} Nessuno lo batte: il migliore è {best.method} con "
                f"{best.mean_hits:.4f} centri per estrazione ({best.excess:+.1f} centri "
                f"sull'intera prova, p = {best.p_value:.2f}). È il risultato atteso. Sei "
                "numeri scelti da un modello fondazionale da 330 milioni di parametri, "
                "dalle frequenze recenti più alte, dai ritardi più lunghi o da un "
                "generatore casuale ottengono lo stesso punteggio, perché l'estrazione "
                "che stanno prevedendo è indipendente da tutto ciò che guardano."
            )
        names = ", ".join(f"{r.method} (p = {r.p_value:.3f})" for r in beat)
        return (
            f"{head} {len(beat)} lo superano al livello del 5%: {names}. Con "
            f"{len(self.results)} metodi in prova, la probabilità che almeno uno "
            f"scenda sotto il 5% per pura fortuna è circa "
            f"{1 - 0.95 ** len(self.results):.0%}. Ripeti la prova su una porzione "
            "diversa dell'archivio prima di considerarlo un risultato."
        )


def walk_forward(
    draws: list[Draw],
    methods: list[str] | None = None,
    n_draws: int = 300,
    picks: int = NUMBERS_PER_DRAW,
    forecaster=None,
    window: int = DEFAULT_WINDOW,
    seed: int = 0,
    min_history: int = MIN_HISTORY,
    progress=None,
) -> ValidationReport:
    """Score each method over the last ``n_draws`` draws of the archive.

    ``forecaster`` is only consulted for the ``"timesfm"`` method; leave it
    None and pass the baselines to run the whole harness with no model.

    The random baseline is re-seeded per target draw, from ``seed`` and the
    target's index, so it is reproducible without being the *same* six numbers
    every time — a fixed set would be a single bet repeated, whose variance is
    not the variance this comparison needs.
    """
    methods = list(methods or ["casuale", "frequenza", "ritardo"])
    unknown = [m for m in methods if m not in METHODS]
    if unknown:
        raise ValueError(f"metodi sconosciuti: {', '.join(unknown)}")
    if "timesfm" in methods and forecaster is None:
        raise ValueError("il metodo timesfm richiede un TimesFMForecaster già caricato")

    total = len(draws)
    start = max(min_history, total - n_draws)
    targets = list(range(start, total))
    if not targets:
        raise ValueError(
            f"{total} estrazioni non bastano per valutare alcunché con uno storico "
            f"minimo di {min_history}"
        )

    hits: dict[str, list[int]] = {m: [] for m in methods}
    for step, i in enumerate(targets):
        history = draws[:i]
        actual = set(draws[i].numbers)
        for method in methods:
            picked = _pick(method, history, picks, window, seed + i, forecaster)
            hits[method].append(len(actual & set(picked)))
        if progress and step % 10 == 0:
            progress(
                f"Valutazione estrazione {step + 1} di {len(targets)}…",
                step / len(targets),
            )

    mean, variance = hypergeom_moments(NUMBER_MAX, NUMBERS_PER_DRAW, picks)
    sd = variance ** 0.5
    n = len(targets)
    null_pmf = [hypergeom_pmf(NUMBER_MAX, NUMBERS_PER_DRAW, picks, k) for k in range(picks + 1)]
    p_three_plus = sum(null_pmf[3:])

    results = []
    for method in methods:
        series = hits[method]
        histogram = [series.count(k) for k in range(picks + 1)]
        total_hits = sum(series)
        # The z is on the *total*, not on the mean of a single draw: n
        # independent draws, each with the hypergeometric variance above.
        z = (total_hits - mean * n) / ((variance * n) ** 0.5) if variance > 0 else 0.0
        chi2, dof, chi2_p = chi_square_goodness_of_fit(
            [float(h) for h in histogram], [n * p for p in null_pmf]
        )
        results.append(MethodResult(
            method=method,
            draws_scored=n,
            picks_per_draw=picks,
            total_hits=total_hits,
            histogram=histogram,
            expected_mean=mean,
            expected_sd=sd,
            z=z,
            p_value=two_sided_normal_p(z),
            chi2=chi2,
            chi2_dof=dof,
            chi2_p=chi2_p,
            best_draw_hits=max(series) if series else 0,
            three_or_more=sum(1 for h in series if h >= 3),
            expected_three_or_more=n * p_three_plus,
        ))

    if progress:
        progress("Validazione completata.", 1.0)
    return ValidationReport(
        results=results,
        draws_scored=n,
        first_target=draws[targets[0]],
        last_target=draws[targets[-1]],
        picks_per_draw=picks,
    )


def _pick(
    method: str, history: list[Draw], picks: int, window: int, seed: int, forecaster
) -> list[int]:
    """The ``picks`` numbers a method would play given only ``history``."""
    if method == "timesfm":
        scores = forecaster.score_numbers(history)
    elif method == "frequenza":
        scores = frequency_scores(history, window)
    elif method == "ritardo":
        scores = gap_scores(history)
    else:
        scores = random_scores(seed)
    return rank_numbers(scores)[:picks]
