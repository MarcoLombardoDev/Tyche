# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
local_file.py — Tyche

Imports a file the user downloaded by hand. Every archive site offers a CSV,
XLS or TXT export somewhere, and this is the path that works when the scraper
does not, when the site is behind a consent wall, or when the machine running
Tyche has no internet at all.

Because the point is to accept whatever the user actually has, the parser
sniffs rather than demands. It tries, in order:

1. Tyche's own canonical CSV, recognised by its header — so exporting an
   archive and re-importing it is lossless.
2. Any CSV with a **labelled header**: ``DATA;CONCORSO;N1;…;N6;JOLLY;SUPERSTAR``
   and the variants of it the Italian archive sites export, in whichever of
   ``;``, ``,`` or tab they chose. Column names beat positions whenever they
   exist, and this is why.
3. The twelve-column bulk format, recognised by shape.
4. A generic line scan: on each line, a date and then at least six distinct
   integers in 1–90. The last resort, for files with no header at all.

**The order matters, and step 2 was added because step 4 got it wrong.** The
export from estrazioni.it puts the contest number *after* the date —
``03/12/1997;87;20;36;39;41;72;76;88;00`` — and 87 is a perfectly good
SuperEnalotto number, so the positional scan read the draw as
``20 36 39 41 72 87`` and the Jolly as 76. Every value was plausible, nothing
raised, and the archive would have been quietly wrong in every row that
carries a contest number. The HTML scraper avoids the mirror image of this by
ignoring integers *before* the date; no positional rule can cover both
layouts, which is the argument for reading the header when there is one.

If none of the four yields a single draw, that is an error and not an empty
result. "Imported 0 draws" reads like "the file was already up to date", which
is the one thing it never means here.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from core.archive import (
    CSV_HEADER,
    NUMBER_MAX,
    NUMBER_MIN,
    NUMBERS_PER_DRAW,
    ArchiveError,
    Draw,
    _parse_date,
)
from core.sources.base import DrawSource, ProgressCallback, SourceError, assign_contest_numbers
from core.sources.bulk_archive import EXPECTED_COLUMNS, parse_bulk_csv
from core.sources.html_table import _find_date

_INT = re.compile(r"\d+")


class LocalFileSource(DrawSource):
    """Import draws from a file on disk. The fallback that cannot break."""

    name = "local-file"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def describe(self) -> str:
        return f"Import manuale da {self.path}"

    def fetch(self, progress: ProgressCallback = None) -> list[Draw]:
        if not self.path.exists():
            raise SourceError(f"{self.path}: file inesistente")
        self._report(progress, f"Leggo {self.path.name}…", 0.2)
        text = self.path.read_text(encoding="utf-8", errors="replace")
        draws = parse_any(text, source=f"{self.name}:{self.path.name}")
        self._report(
            progress, f"{len(draws)} estrazioni lette da {self.path.name}.", 1.0
        )
        return draws


def parse_any(text: str, source: str = "local-file") -> list[Draw]:
    """Try each known layout in turn. Raises SourceError if all of them fail."""
    for parser in (_parse_canonical, _parse_labelled, _parse_bulk, _parse_freeform):
        try:
            draws = parser(text, source)
        except SourceError:
            continue
        if draws:
            return draws
    raise SourceError(
        "nessuna estrazione riconosciuta — servono l'intestazione CSV di Tyche, "
        "un'intestazione con una colonna data e sei colonne di numeri, il formato "
        "in blocco a dodici colonne, oppure righe con una data seguita da sei "
        "numeri distinti fra 1 e 90"
    )


def _parse_canonical(text: str, source: str) -> list[Draw]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not set(CSV_HEADER[:9]).issubset(reader.fieldnames):
        raise SourceError("not the canonical format")
    draws = []
    for row in reader:
        try:
            draws.append(Draw.from_row(row))
        except (ArchiveError, KeyError, ValueError):
            continue
    return draws


# Header aliases, upper-cased and stripped. Deliberately short lists: a name
# nobody has actually seen in an export is a guess that makes a
# misidentification more likely, not less.
_DATE_NAMES = ("DATA", "DATE", "DATA ESTRAZIONE", "ESTRAZIONE", "GIORNO")
_CONTEST_NAMES = ("CONCORSO", "N. CONCORSO", "NUMERO CONCORSO", "CONTEST", "ID")
_JOLLY_NAMES = ("JOLLY", "NUMERO JOLLY", "J")
_SUPERSTAR_NAMES = ("SUPERSTAR", "SUPER STAR", "SS", "STELLA")


def _parse_labelled(text: str, source: str) -> list[Draw]:
    """Read a CSV that names its columns, in ``;``, ``,`` or tab.

    Six number columns are found by name — ``N1``…``N6``, ``NUMERO1``…, or a
    bare ``1``…``6`` — and everything else is optional. A missing contest
    number is filled in as the ordinal within its year, which is safe here
    because these exports are whole-archive dumps; estrazioni.it stops
    printing it from 2014 onwards and 2,008 of its 4,260 rows have the field
    empty.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise SourceError("empty file")
    header_line = lines[0].lstrip("\ufeff")
    delimiter = max((";", ",", "\t"), key=header_line.count)
    if header_line.count(delimiter) < 6:
        raise SourceError("no delimiter separating at least seven columns")

    header = [c.strip().strip('"').upper() for c in header_line.split(delimiter)]
    index = {name: i for i, name in enumerate(header)}

    def find(names: tuple[str, ...]) -> int | None:
        for name in names:
            if name in index:
                return index[name]
        return None

    date_at = find(_DATE_NAMES)
    number_at = []
    for n in range(1, 7):
        column = find((f"N{n}", f"NUMERO{n}", f"NUMERO {n}", f"NUM{n}", str(n)))
        if column is None:
            break
        number_at.append(column)
    if date_at is None or len(number_at) != 6:
        raise SourceError("header does not name a date column and six number columns")

    contest_at = find(_CONTEST_NAMES)
    jolly_at = find(_JOLLY_NAMES)
    superstar_at = find(_SUPERSTAR_NAMES)

    def cell(fields: list[str], at: int | None) -> str:
        if at is None or at >= len(fields):
            return ""
        return fields[at].strip().strip('"')

    rows: list[dict] = []
    skipped = 0
    for line in lines[1:]:
        fields = line.split(delimiter)
        try:
            rows.append({
                "date": _parse_date(cell(fields, date_at)),
                "contest": int(cell(fields, contest_at) or 0) or None,
                "numbers": [int(cell(fields, at)) for at in number_at],
                "jolly": int(cell(fields, jolly_at) or 0),
                "superstar": int(cell(fields, superstar_at) or 0),
            })
        except (ArchiveError, ValueError):
            skipped += 1
    if not rows:
        raise SourceError("header looked right but no row parsed")
    if skipped:
        print(f"[LocalFile] skipped {skipped} unusable rows")

    assign_contest_numbers(rows)
    draws = []
    for row in rows:
        try:
            draws.append(Draw(
                date=row["date"], contest=row["contest"], numbers=tuple(row["numbers"]),
                jolly=row["jolly"], superstar=row["superstar"], source=source,
            ))
        except ArchiveError as exc:
            print(f"[LocalFile] dropping implausible row: {exc}")
    return draws


def _parse_bulk(text: str, source: str) -> list[Draw]:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if len(first.split(",")) != EXPECTED_COLUMNS:
        raise SourceError("not the bulk format")
    return parse_bulk_csv(text, source=source)


def _parse_freeform(text: str, source: str) -> list[Draw]:
    """One line, one draw: a date, then the balls. Separator-agnostic.

    The date is located first and everything before it ignored, so a leading
    contest number cannot be mistaken for a ball — the same rule as the HTML
    scraper, and worth stating twice because breaking it in one place and not
    the other would give two importers that disagree about the same file.
    """
    rows: list[dict] = []
    for line in text.splitlines():
        found = _find_date(line)
        if found is None:
            continue
        # Cut the line at the end of the matched date so its own digits, and
        # anything printed before it, stay out of the ball list.
        tail = line[line.index(str(found.year)) + 4:] if str(found.year) in line else ""
        balls = [int(t) for t in _INT.findall(tail) if NUMBER_MIN <= int(t) <= NUMBER_MAX]
        if len(balls) < NUMBERS_PER_DRAW:
            continue
        numbers = balls[:NUMBERS_PER_DRAW]
        if len(set(numbers)) != NUMBERS_PER_DRAW:
            continue
        rest = balls[NUMBERS_PER_DRAW:]
        rows.append({
            "date": found, "contest": None, "numbers": numbers,
            "jolly": rest[0] if rest else 0,
            "superstar": rest[1] if len(rest) > 1 else 0,
        })
    if not rows:
        raise SourceError("no date-plus-six-numbers lines found")
    assign_contest_numbers(rows)
    draws = []
    for row in rows:
        try:
            draws.append(Draw(
                date=row["date"], contest=row["contest"], numbers=tuple(row["numbers"]),
                jolly=row["jolly"], superstar=row["superstar"], source=source,
            ))
        except ArchiveError:
            continue
    return draws
