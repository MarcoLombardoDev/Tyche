# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

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
from core.localise import it_date, it_number


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
            last_seen=it_date(draws[i].date) if i is not None else "mai",
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
        return ["L'archivio è vuoto. Aggiornalo dalla scheda Archivio."]
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
        f"{it_number(total)} estrazioni dal {it_date(draws[0].date)} "
        f"al {it_date(draws[-1].date)}.",
        f"Ogni numero è atteso {expected:.0f} volte, più o meno {sigma:.0f}.",
        f"Più estratto: {hottest} ({tally[hottest]}). Meno estratto: {coldest} "
        f"({tally[coldest]}). Differenza {spread}, che per novanta numeri con uno "
        f"scarto tipo di {sigma:.0f} è quanto produce il caso.",
        f"Ritardo più lungo in corso: il {longest}, {gaps[longest]} estrazioni. La sua "
        f"probabilità di uscire alla prossima è {p:.4f} — la stessa di ogni altro "
        f"numero.",
    ]


# ── the three tables as text ─────────────────────────────────
#
# Here rather than in the panel that draws them, for two reasons. They moved
# once already — the Statistics tab was folded into the Archive tab in 0.11.0 —
# and text that lives in the panel moves with the panel and gets rewritten on
# the way. And a report built in `core/` can be checked by a test that needs
# no display, which the panel's own `refresh` could not be.

def number_report(draws: list[Draw]) -> str:
    """The ninety numbers: how often each came out, against how often expected."""
    rows = number_table(draws)
    flagged = sum(1 for r in rows if r.unusual)
    header = (
        # "z", not "σ". The column is how many standard deviations the count
        # sits from its expectation; labelling it with the symbol for the
        # standard deviation itself invites reading it as one.
        f"{'n':>3} {'uscite':>7} {'attese':>7} {'z':>7}  "
        f"{'rit.':>5} {'rit.atteso':>11}  {'ultima':<12}"
    )
    # Above the table, not below it. Ninety rows do not fit the box, so a note
    # printed after them is a note nobody reaches — which is what happened to
    # this one until the screenshots showed it off-screen.
    lines = [
        "z = di quanti scarti tipo le uscite di un numero distano dall'attesa.",
        "rit. = estrazioni dall'ultima uscita.",
        f"'<' segna i {flagged} numeri su 90 che distano più di due scarti tipo.",
        "Fra quattro e cinque è quanto producono estrazioni indipendenti — il 5%",
        "di novanta fa 4,5 — quindi una tabella senza nessun segno sarebbe",
        "quella sorprendente.",
        "",
        header,
        "─" * len(header),
    ]
    for r in rows:
        flag = "  <" if r.unusual else ""
        lines.append(
            f"{r.number:>3} {r.count:>7} {r.expected:>7.1f} {r.sigma:>+7.2f}  "
            f"{r.gap:>5} {r.expected_gap:>11.1f}  {r.last_seen:<12}{flag}"
        )
    return "\n".join(lines)


def decade_report(draws: list[Draw]) -> str:
    """Nine bands of exactly ten numbers, so the ratios compare directly."""
    header = f"{'decina':<8} {'osservate':>10} {'attese':>9} {'rapporto':>9}"
    lines = [header, "─" * len(header)]
    for label, observed, expected, ratio in decade_table(draws):
        lines.append(f"{label:<8} {observed:>10} {expected:>9.1f} {ratio:>9.3f}")
    lines += [
        "",
        "Nove decine da esattamente dieci numeri, quindi le attese sono uguali e i",
        "rapporti si confrontano direttamente. Tracciare le fasce come 1–9, 10–19,",
        "… 80–90 — come si fa spesso — dà una fascia da nove numeri e una da undici,",
        "e gli ottanta sembrano allora sempre caldi solo per la loro ampiezza.",
    ]
    return "\n".join(lines)


def pairs_report(draws: list[Draw], limit: int = 25) -> str:
    """The top of four thousand Poisson counts, which is not a finding."""
    header = f"{'coppia':<9} {'insieme':>9} {'attese':>9}"
    # Twenty-five rows do not fit the box either, so this note goes first for
    # the same reason. The decade table above keeps its note below, because
    # nine rows and a heading do fit and it reads as a conclusion.
    lines = [
        "Sono 4.005 le coppie in gara per questa lista, quindi la cima è il massimo",
        "di quattromila conteggi grosso modo poissoniani e sta per costruzione a",
        "diversi scarti tipo sopra la media. Questa tabella non ha contenuto",
        "predittivo: è qui perché ometterla farebbe nascere la domanda su che cosa",
        "avrebbe mostrato.",
        "",
        header,
        "─" * len(header),
    ]
    for a, b, observed, expected in top_pairs(draws, limit):
        lines.append(f"{a:>2}–{b:<6} {observed:>9} {expected:>9.1f}")
    return "\n".join(lines)
