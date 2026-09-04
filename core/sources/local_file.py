# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

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
2. The twelve-column bulk format, recognised by shape.
3. A generic line scan: on each line, a date and then at least six distinct
   integers in 1–90. This is the same positional rule the HTML scraper uses,
   for the same reason, and it swallows most of the semicolon- and
   tab-separated exports without needing to know which one it was handed.

If none of the three yields a single draw, that is an error and not an empty
result. "Imported 0 draws" reads like "the file was already up to date", which
is the one thing it never means here.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from core.archive import CSV_HEADER, NUMBER_MAX, NUMBER_MIN, NUMBERS_PER_DRAW, ArchiveError, Draw
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
        return f"Manual import from {self.path}"

    def fetch(self, progress: ProgressCallback = None) -> list[Draw]:
        if not self.path.exists():
            raise SourceError(f"{self.path}: no such file")
        self._report(progress, f"Reading {self.path.name}…", 0.2)
        text = self.path.read_text(encoding="utf-8", errors="replace")
        draws = parse_any(text, source=f"{self.name}:{self.path.name}")
        self._report(progress, f"{len(draws):,} draws read from {self.path.name}.", 1.0)
        return draws


def parse_any(text: str, source: str = "local-file") -> list[Draw]:
    """Try each known layout in turn. Raises SourceError if all of them fail."""
    for parser in (_parse_canonical, _parse_bulk, _parse_freeform):
        try:
            draws = parser(text, source)
        except SourceError:
            continue
        if draws:
            return draws
    raise SourceError(
        "no draws recognised — expected either Tyche's own CSV header, the "
        "twelve-column bulk format, or lines carrying a date followed by six "
        "distinct numbers in 1–90"
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
