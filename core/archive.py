# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
archive.py — Tyche

The canonical draw record and the one file every other module reads.

A SuperEnalotto draw is six distinct numbers from 1–90, plus a *Jolly* drawn
from the remaining 84, plus — since February 2006 — a *SuperStar* drawn
independently from a second 1–90 pool and therefore free to repeat one of the
six. Those three facts drive every validation rule below, and getting the
third one wrong is the classic bug: a SuperStar equal to one of the main
numbers is not corrupt data.

Two numbering systems coexist and neither is a primary key on its own. The
contest number restarts at 1 every January, so ``8`` identifies nothing;
``2020/8`` does. :attr:`Draw.draw_id` is that pair, and it is what dedup keys
on when archives from different sources are merged.

The stored file is a plain CSV with a header, sorted by date. Not Parquet, not
SQLite: the whole history since 1997 is under two thousand rows and a quarter
of a megabyte, it wants to be greppable and diffable, and a format the user
can open in a spreadsheet removes an entire class of support question.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from core.localise import it_date as _it_date

# The SuperEnalotto wheel: 90 numbers, six drawn.
NUMBER_MIN = 1
NUMBER_MAX = 90
NUMBERS_PER_DRAW = 6
ALL_NUMBERS = tuple(range(NUMBER_MIN, NUMBER_MAX + 1))

# 3 December 1997: the first SuperEnalotto draw. Anything before that date in a
# source file belongs to Enalotto, its 1961–1997 predecessor — same 90-number
# wheel, different game, different draw machinery. Tyche keeps those rows out
# of the archive by default rather than silently treating them as one series.
FIRST_DRAW_DATE = date(1997, 12, 3)

# SuperStar was added on 2 February 2006. Rows before it carry 0, meaning
# "not played", which is not the same as "drew a zero".
SUPERSTAR_FROM = date(2006, 2, 2)

CSV_HEADER = [
    "date", "year", "contest",
    "n1", "n2", "n3", "n4", "n5", "n6",
    "jolly", "superstar", "source",
]


class ArchiveError(ValueError):
    """A draw that cannot be represented, or a file that cannot be parsed."""


@dataclass(frozen=True, slots=True)
class Draw:
    """One SuperEnalotto draw.

    ``numbers`` is always stored ascending. The order the balls left the
    machine is not published, carries no information the game uses, and
    letting it vary would make two records of the same draw compare unequal.

    ``jolly`` and ``superstar`` both use 0 for "not on record", which is not
    the same as "drew a zero". For the SuperStar that is a fact about the game
    — it did not exist before February 2006. For the Jolly it is a fact about
    the sources: every real draw has one, but some archive pages do not print
    it, and a row missing its Jolly is still six perfectly good main numbers.
    Nothing in Tyche's analysis reads the Jolly, so dropping such a row would
    cost real data to preserve a field nothing uses.
    """

    date: date
    contest: int
    numbers: tuple[int, ...]
    jolly: int
    superstar: int = 0
    source: str = ""
    year: int = field(default=0)

    def __post_init__(self):
        object.__setattr__(self, "numbers", tuple(sorted(self.numbers)))
        if not self.year:
            object.__setattr__(self, "year", self.date.year)
        self.validate()

    def validate(self) -> None:
        """Raise :class:`ArchiveError` unless the row is a possible draw.

        Called from ``__post_init__``, so an invalid Draw cannot be
        constructed at all. Parsers therefore never need their own checks —
        they build a Draw and let it refuse.
        """
        if len(self.numbers) != NUMBERS_PER_DRAW:
            raise ArchiveError(
                f"{self.draw_id}: {len(self.numbers)} numbers, expected {NUMBERS_PER_DRAW}"
            )
        if len(set(self.numbers)) != NUMBERS_PER_DRAW:
            raise ArchiveError(f"{self.draw_id}: repeated number in {self.numbers}")
        for n in self.numbers:
            if not NUMBER_MIN <= n <= NUMBER_MAX:
                raise ArchiveError(f"{self.draw_id}: {n} is outside 1–90")
        if self.jolly and not NUMBER_MIN <= self.jolly <= NUMBER_MAX:
            raise ArchiveError(f"{self.draw_id}: jolly {self.jolly} is outside 1–90")
        if self.jolly and self.jolly in self.numbers:
            # The Jolly comes out of the same drum, after the six, so it
            # cannot repeat one of them. When it appears to, the row has been
            # mis-parsed — almost always a column offset. Checked against the
            # 5,038-row bulk archive: it never happens there, so the rule is
            # safe to enforce rather than merely warn about.
            raise ArchiveError(f"{self.draw_id}: jolly {self.jolly} repeats a main number")
        if self.superstar and not NUMBER_MIN <= self.superstar <= NUMBER_MAX:
            raise ArchiveError(f"{self.draw_id}: superstar {self.superstar} is outside 1–90")
        if self.contest < 1:
            raise ArchiveError(f"{self.draw_id}: contest number must be positive")

    @property
    def draw_id(self) -> str:
        """``YYYY/N`` — the identifier the operator prints on a receipt."""
        return f"{self.year}/{self.contest}"

    @property
    def has_superstar(self) -> bool:
        return self.superstar > 0

    def to_row(self) -> list[str]:
        return [
            self.date.isoformat(), str(self.year), str(self.contest),
            *(str(n) for n in self.numbers),
            str(self.jolly), str(self.superstar), self.source,
        ]

    @classmethod
    def from_row(cls, row: dict) -> Draw:
        return cls(
            date=_parse_date(row["date"]),
            contest=int(row["contest"]),
            numbers=tuple(int(row[f"n{i}"]) for i in range(1, 7)),
            jolly=int(row["jolly"]),
            superstar=int(row.get("superstar") or 0),
            source=row.get("source", ""),
            year=int(row.get("year") or 0),
        )


def _parse_date(text: str) -> date:
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ArchiveError(f"unrecognised date: {text!r}")


def load_archive(path: Path) -> list[Draw]:
    """Read the canonical CSV. A missing file is an empty archive, not an error.

    A row that fails validation is skipped with a message rather than killing
    the load: one corrupt line in a 1,700-row history should cost the user
    that line, not the application.
    """
    if not Path(path).exists():
        return []
    draws: list[Draw] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                draws.append(Draw.from_row(row))
            except (ArchiveError, KeyError, ValueError) as exc:
                print(f"[Archive] skipping malformed row: {exc}")
    draws.sort(key=lambda d: (d.date, d.contest))
    return draws


def save_archive(path: Path, draws: list[Draw]) -> int:
    """Write the archive, sorted, creating parent directories. Returns the count.

    Writes through a temporary file in the same directory and renames it over
    the target, because the alternative is that an interruption halfway
    through leaves the user with a truncated history and no copy of the whole
    one. ``Path.replace`` is atomic on both platforms Tyche runs on.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(draws, key=lambda d: (d.date, d.contest))
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        for d in ordered:
            writer.writerow(d.to_row())
    tmp.replace(path)
    return len(ordered)


def merge_draws(existing: list[Draw], incoming: list[Draw]) -> tuple[list[Draw], int, int]:
    """Combine two archives, keyed on the draw *date*.

    Returns ``(merged, added, updated)``.

    The key is the date and not ``draw_id``, which is the more obvious choice
    and the wrong one. Contest numbers are the least reliable field any source
    publishes: the mirrored bulk archive labels the first nine draws of 1999
    as 1998, so nine real draws share a ``draw_id`` with nine other real
    draws. Keying on that identifier silently deletes one of each pair. Dates
    are the natural key — one SuperEnalotto draw per date, always — and where
    two rows still claim the same date, one of them is wrong and
    :func:`integrity_report` says so rather than the merge quietly choosing.

    Incoming wins on a conflict, with one exception that matters in practice:
    an incoming row whose SuperStar is 0 does not erase a SuperStar already on
    record. The bulk historical files tend to omit it while the per-year pages
    carry it, so a refresh from the wrong source would otherwise quietly strip
    twenty years of SuperStar data. The same rule applies to the Jolly.
    """
    by_date = {d.date: d for d in existing}
    added = updated = 0
    for draw in incoming:
        old = by_date.get(draw.date)
        if old is None:
            by_date[draw.date] = draw
            added += 1
            continue
        superstar = draw.superstar or old.superstar
        jolly = draw.jolly or old.jolly
        if (superstar, jolly) != (draw.superstar, draw.jolly):
            draw = Draw(
                date=draw.date, contest=draw.contest, numbers=draw.numbers,
                jolly=jolly, superstar=superstar,
                source=draw.source, year=draw.year,
            )
        if draw.to_row()[:-1] != old.to_row()[:-1]:
            by_date[draw.date] = draw
            updated += 1
    merged = sorted(by_date.values(), key=lambda d: (d.date, d.contest))
    return merged, added, updated


@dataclass(frozen=True)
class IntegrityIssue:
    """One thing wrong with an archive, and how much it matters."""

    kind: str
    severity: str      # "error" — the data is wrong; "warning" — it might be
    message: str


def integrity_report(draws: list[Draw]) -> list[IntegrityIssue]:
    """Everything suspicious about an archive, in one pass.

    Written because the mirrored bulk archive turned out to be wrong in a way
    no amount of reading the parser would have revealed: 3,076 rows that all
    validate individually, nine of which carry the wrong year. Per-row
    validation cannot see that. Only looking at the sequence can.

    The four checks, in decreasing order of how much they should worry a
    reader:

    - **duplicate dates** — two different draws claiming one date. One is
      fabricated or mislabelled, and it is polluting every statistic.
    - **duplicate contest ids** — the 1999-labelled-1998 defect. Harmless to
      the numbers, fatal to anything that trusts ``draw_id``.
    - **contest gaps** — a year missing contests it should have. Usually a
      partial import rather than corruption, but a partial import analysed as
      if complete gives a confidently wrong frequency table.
    - **contest and date disagree** — rows whose contest order does not match
      their date order within a year, which is how a mislabelled block shows
      up when it happens not to collide with anything.

    An empty list means the archive is internally consistent. It does not mean
    the archive is *correct*: only a second source can say that.
    """
    issues: list[IntegrityIssue] = []
    if not draws:
        return issues

    seen_dates: dict[date, Draw] = {}
    for draw in draws:
        clash = seen_dates.get(draw.date)
        if clash is not None and clash.numbers != draw.numbers:
            issues.append(IntegrityIssue(
                "duplicate-date", "error",
                f"{_it_date(draw.date)}: due estrazioni diverse nella stessa data "
                f"({clash.numbers} e {draw.numbers})",
            ))
        seen_dates.setdefault(draw.date, draw)

    seen_ids: dict[str, Draw] = {}
    for draw in draws:
        clash = seen_ids.get(draw.draw_id)
        if clash is not None:
            issues.append(IntegrityIssue(
                "duplicate-contest", "error",
                f"il concorso {draw.draw_id} compare due volte "
                f"({_it_date(clash.date)} e {_it_date(draw.date)}) — uno dei due "
                "ha l'anno sbagliato",
            ))
        seen_ids.setdefault(draw.draw_id, draw)

    by_year: dict[int, list[Draw]] = {}
    for draw in draws:
        by_year.setdefault(draw.year, []).append(draw)
    # The first and last year of any archive are partial by construction — the
    # game started in December 1997 and today is not the 31st of December — so
    # a gap there is the shape of the data, not a defect. Reporting it trains
    # the reader to ignore the whole section.
    partial_years = {min(by_year), max(by_year)}
    for year in sorted(by_year):
        year_draws = by_year[year]
        contests = sorted(d.contest for d in year_draws)
        missing = sorted(set(range(1, contests[-1] + 1)) - set(contests))
        if missing and year not in partial_years:
            issues.append(IntegrityIssue(
                "contest-gap", "warning",
                f"{year}: mancano i concorsi {_ranges(missing)} su 1–{contests[-1]}",
            ))
        by_date_order = [d.contest for d in sorted(year_draws, key=lambda d: d.date)]
        if by_date_order != sorted(by_date_order):
            issues.append(IntegrityIssue(
                "contest-order", "warning",
                f"{year}: i numeri di concorso non crescono con la data",
            ))
    return issues


def _ranges(values: list[int]) -> str:
    """``[1,2,3,7]`` as ``"1–3, 7"`` — a gap list the user can actually read."""
    out: list[str] = []
    start = prev = values[0]
    for v in values[1:]:
        if v == prev + 1:
            prev = v
            continue
        out.append(str(start) if start == prev else f"{start}–{prev}")
        start = prev = v
    out.append(str(start) if start == prev else f"{start}–{prev}")
    return ", ".join(out)


def superenalotto_only(draws: list[Draw]) -> list[Draw]:
    """Drop anything before 3 December 1997.

    The widely mirrored bulk archives start in 1961 with Enalotto, whose rows
    look identical and are not the same game. Analysing them as one continuous
    series is the single easiest way to produce a confidently wrong statistic
    here, so the filter is applied on import rather than left to the caller.
    """
    return [d for d in draws if d.date >= FIRST_DRAW_DATE]


def describe_archive(draws: list[Draw]) -> dict:
    """Summary for the status bar and the tests: counts, span, coverage."""
    if not draws:
        return {"count": 0, "first": None, "last": None, "years": 0, "with_superstar": 0}
    return {
        "count": len(draws),
        "first": draws[0].date,
        "last": draws[-1].date,
        "years": draws[-1].date.year - draws[0].date.year + 1,
        "with_superstar": sum(1 for d in draws if d.has_superstar),
    }


def repair_year_offset(draws: list[Draw]) -> tuple[list[Draw], list[str]]:
    """Move a block of draws labelled with the wrong year back where it belongs.

    The mirrored bulk archive carries the first nine draws of 1999 under the
    year 1998. :func:`integrity_report` finds them as nine duplicated contest
    ids; this puts them right, and from evidence rather than a hardcoded list
    of dates, so the same defect at a different boundary is fixed too.

    Pass the draws in *source order*. The repair uses position as a
    tie-breaker, and sorting first throws that information away.

    **Pass one — identify the block.** For each duplicated ``draw_id``, both
    occurrences are tested as the mislabelled one. A candidate is accepted
    only when shifting it forward by exactly one year satisfies all four of:

    - the target ``(year, contest)`` slot is vacant;
    - the shifted date is not already taken by another draw;
    - the shifted date falls before every draw the target year already has,
      which is what "contests 1 to 9 of that year" means;
    - the shifted date lands on a weekday the target year actually draws on.

    That last condition is what makes the repair evidence-based rather than a
    coin toss. In the real case both occurrences pass the first three: 1998-01-02
    and 1998-01-03 both move into a vacant 1999/1 ahead of 1999's first
    recorded draw. Only one lands on a day the game is played — 1999-01-02 is
    a Saturday, 1999-01-03 a Sunday, and SuperEnalotto has never drawn on a
    Sunday.

    **Pass two — the block is a block.** Four of the nine duplicates cannot be
    resolved that way, and two of those cannot be resolved by any test on
    dates at all, because both occurrences carry the *same* date: the mirror
    holds two different draws on 1998-01-07 and two on 1998-01-27. What
    settles them is that they are not nine independent defects, they are one
    mislabelled block, contiguous in the file. Once pass one anchors a member,
    the rest are the occurrences on the same side of their pair *by position*
    — in the real file, lines 2076–2084 rather than 1972–1980.

    Position, and not date, is what "same side" has to mean. The first
    attempt at this used the earlier date, which agrees with position for
    seven of the nine pairs and disagrees for exactly the two that share a
    date — so it quietly swapped the numbers of 1998/2 with 1999/2 and 1998/8
    with 1999/8, and left an archive that passed every integrity check. Two
    criteria that agree most of the time are one criterion and one bug.

    Pass two therefore runs only when pass one anchored something, and the
    whole set of moved rows must form one unbroken run of file positions. A
    scattered set is not a mislabelled block, whatever else it is, and nothing
    is moved. Every decision comes back as a note: a wrong repair is worse
    than a flagged defect.
    """
    by_id: dict[str, list[Draw]] = {}
    for draw in draws:
        by_id.setdefault(draw.draw_id, []).append(draw)
    duplicates = {k: v for k, v in by_id.items() if len(v) > 1}
    if not duplicates:
        return list(draws), []

    position = {id(d): i for i, d in enumerate(draws)}
    slots = {(d.year, d.contest) for d in draws}
    dates = {d.date for d in draws}
    # Snapshots of the archive as it stands *before* any repair. Recomputing
    # them as rows move would make each move invalidate the next: the first
    # repaired row becomes the target year's earliest draw, and every
    # subsequent candidate then fails the "before everything else" test.
    first_date_of_year: dict[int, date] = {}
    weekdays_of_year: dict[int, set[int]] = {}
    for d in draws:
        prev = first_date_of_year.get(d.year)
        if prev is None or d.date < prev:
            first_date_of_year[d.year] = d.date
        weekdays_of_year.setdefault(d.year, set()).add(d.date.weekday())

    def viable(candidate: Draw) -> bool:
        target_year = candidate.year + 1
        try:
            shifted = candidate.date.replace(year=candidate.date.year + 1)
        except ValueError:
            return False  # 29 February, which no draw calendar depends on
        if (target_year, candidate.contest) in slots or shifted in dates:
            return False
        known_first = first_date_of_year.get(target_year)
        if known_first is not None and shifted >= known_first:
            return False
        known_weekdays = weekdays_of_year.get(target_year)
        return not (known_weekdays and shifted.weekday() not in known_weekdays)

    def side(candidate: Draw, group: list[Draw]) -> str:
        """"early" or "late" — which half of its duplicate pair, by file position."""
        first = min(group, key=lambda d: position[id(d)])
        return "early" if candidate is first else "late"

    moved: dict[int, Draw] = {}
    notes: list[str] = []
    unresolved: list[tuple[str, list[Draw]]] = []
    anchor_sides: set[str] = set()

    def apply(original: Draw, why: str) -> None:
        shifted_date = original.date.replace(year=original.date.year + 1)
        replacement = Draw(
            date=shifted_date, contest=original.contest, numbers=original.numbers,
            jolly=original.jolly, superstar=original.superstar,
            source=f"{original.source}+repaired", year=shifted_date.year,
        )
        moved[id(original)] = replacement
        slots.discard((original.year, original.contest))
        slots.add((replacement.year, replacement.contest))
        dates.discard(original.date)
        dates.add(replacement.date)
        notes.append(
            f"{original.draw_id} on {original.date} relabelled "
            f"{replacement.draw_id} on {shifted_date} ({why})"
        )

    for draw_id, group in sorted(duplicates.items()):
        candidates = [d for d in group if viable(d)]
        if len(candidates) == 1:
            anchor_sides.add(side(candidates[0], group))
            apply(candidates[0], "only occurrence that lands on a valid draw day")
        else:
            unresolved.append((draw_id, group))

    if unresolved and len(anchor_sides) == 1:
        anchor = anchor_sides.pop()
        for draw_id, group in unresolved:
            picks = [d for d in group if side(d, group) == anchor]
            if len(picks) == 1 and (picks[0].year + 1, picks[0].contest) not in slots:
                apply(picks[0], f"same side of the block as the anchored repair ({anchor})")
            else:
                notes.append(f"{draw_id}: duplicated and not repairable — left as is")
    else:
        for draw_id, _ in unresolved:
            notes.append(f"{draw_id}: duplicated with no anchor to resolve it — left as is")

    positions_moved = sorted(position[id(d)] for d in draws if id(d) in moved)
    if positions_moved and positions_moved[-1] - positions_moved[0] != len(positions_moved) - 1:
        return list(draws), [
            "repair abandoned: the rows it would have moved are scattered through "
            f"the file (positions {positions_moved[0]}–{positions_moved[-1]} for "
            f"{len(positions_moved)} rows), which is not one mislabelled block"
        ]

    repaired = [moved.get(id(d), d) for d in draws]
    repaired.sort(key=lambda d: (d.date, d.contest))
    return repaired, notes


# ─────────────────────────────────────────────────────────────
# Is the archive current, and what would an import do to it?
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Freshness:
    """How far behind the archive is, and how many draws that is."""

    last_date: date | None
    days_behind: int
    average_interval_days: float
    estimated_missing: int

    @property
    def stale(self) -> bool:
        """Behind by more than about two draws.

        One missed draw is a user who has not clicked update since Tuesday.
        Three is an archive that has stopped being maintained, which is the
        state the bulk mirror leaves it in permanently.
        """
        return self.estimated_missing >= 2

    def describe(self) -> str:
        if self.last_date is None:
            return "L'archivio è vuoto."
        if not self.stale:
            when = "oggi" if self.days_behind == 0 else (
                "1 giorno fa" if self.days_behind == 1 else f"{self.days_behind} giorni fa"
            )
            return f"Aggiornato al {_it_date(self.last_date)} ({when})."
        return (
            f"L'ultima estrazione registrata è del {_it_date(self.last_date)}, "
            f"{self.days_behind} giorni fa — mancano circa {self.estimated_missing} "
            f"estrazioni, alla cadenza dell'archivio di una ogni "
            f"{self.average_interval_days:.1f} giorni."
        )


def freshness(draws: list[Draw], today: date | None = None, sample: int = 50) -> Freshness:
    """How stale the archive is, measured against its own draw cadence.

    The cadence is taken from the last ``sample`` draws rather than hardcoded,
    because SuperEnalotto's schedule has changed repeatedly — twice a week at
    the start, three a week from 2005, a fourth day added later. A constant
    here would be wrong for most of the archive and would quietly become wrong
    again at the next change.

    The *mean* interval, not the median. The question being answered is "how
    many draws happened while nobody was updating", over a horizon of years,
    and at that length the occasional Christmas gap is part of the rate rather
    than an outlier to suppress. On a Tuesday/Thursday/Saturday schedule the
    intervals are 2, 2 and 3 days: the median is 2.0 and overstates the count
    by a sixth, the mean is 2.33 and does not. The median would be the right
    answer to "when is the next one", which is a different question and one
    nothing here asks.
    """
    today = today or date.today()
    if not draws:
        return Freshness(None, 0, 0.0, 0)
    last = max(d.date for d in draws)
    days_behind = max((today - last).days, 0)

    recent = sorted(d.date for d in draws)[-(sample + 1):]
    intervals = [(b - a).days for a, b in zip(recent, recent[1:], strict=False)]
    # Floored at one day: a corrupt archive with several draws on one date
    # would otherwise divide by zero, and an interval under a day is not a
    # schedule this game has ever run.
    average = max(sum(intervals) / len(intervals), 1.0) if intervals else 1.0
    return Freshness(last, days_behind, average, int(days_behind // average))


@dataclass(frozen=True)
class MergePreview:
    """What merging a fetch into the archive would do, before it does it.

    The scraper in :mod:`core.sources.html_table` has never run against a live
    page, so "fetch and write" is the wrong shape for it: a parser that
    silently misreads a column would overwrite good rows with plausible
    nonsense, and the archive has no undo. This is what the Archive tab shows
    the user first.
    """

    added: int
    updated: int
    unchanged: int
    conflicts: list[str]
    new_issues: list[IntegrityIssue]
    first_new: date | None
    last_new: date | None
    samples: list[Draw]

    @property
    def safe(self) -> bool:
        return not self.conflicts and not any(i.severity == "error" for i in self.new_issues)

    def describe(self) -> str:
        if not self.added and not self.updated:
            parts = [
                f"Niente di nuovo: tutte le {self.unchanged} estrazioni scaricate "
                "sono già in archivio."
            ]
        else:
            parts = [
                f"{self.added} estrazioni da aggiungere, {self.updated} da modificare, "
                f"{self.unchanged} già identiche."
            ]
            if self.first_new:
                parts.append(
                    f"Le nuove vanno dal {_it_date(self.first_new)} "
                    f"al {_it_date(self.last_new)}."
                )
        if self.conflicts:
            parts.append(
                f"{len(self.conflicts)} di queste contraddicono un'estrazione già "
                "registrata: " + "; ".join(self.conflicts[:3])
                + ("; …" if len(self.conflicts) > 3 else "")
            )
        errors = [i for i in self.new_issues if i.severity == "error"]
        if errors:
            parts.append(
                f"L'unione introdurrebbe {len(errors)} nuovi errori di integrità."
            )
        return " ".join(parts)


def preview_merge(existing: list[Draw], incoming: list[Draw]) -> MergePreview:
    """Dry-run :func:`merge_draws` and report what it would change.

    A *conflict* is an incoming row whose numbers differ from a stored row for
    the same date. That is the signature of a mis-parse, and it is worth
    separating from an ordinary update — which is usually a row gaining its
    SuperStar or its contest number.
    """
    by_date = {d.date: d for d in existing}
    added = updated = unchanged = 0
    conflicts: list[str] = []
    new_dates: list[date] = []
    for draw in incoming:
        old = by_date.get(draw.date)
        if old is None:
            added += 1
            new_dates.append(draw.date)
            continue
        if old.numbers != draw.numbers:
            conflicts.append(
                f"{_it_date(draw.date)}: in archivio {old.numbers}, "
                f"scaricata {draw.numbers}"
            )
            updated += 1
        elif draw.to_row()[:-1] != old.to_row()[:-1]:
            updated += 1
        else:
            unchanged += 1

    merged, _, _ = merge_draws(existing, incoming)
    before = {(i.kind, i.message) for i in integrity_report(existing)}
    new_issues = [i for i in integrity_report(merged) if (i.kind, i.message) not in before]

    samples = sorted(
        (d for d in incoming if d.date not in by_date), key=lambda d: d.date
    )[-5:]
    return MergePreview(
        added=added,
        updated=updated,
        unchanged=unchanged,
        conflicts=conflicts,
        new_issues=new_issues,
        first_new=min(new_dates) if new_dates else None,
        last_new=max(new_dates) if new_dates else None,
        samples=samples,
    )
