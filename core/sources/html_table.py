# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
html_table.py — Tyche

Scrapes a per-year archive page and pulls draws out of whatever table it
finds. This is the source that keeps the archive current, and it is the one to
read carefully before trusting.

**Never run against the live site.** Every Italian lottery archive host —
superenalotto.it, sisal.it, lottologia.com, estrazionilottooggi.it — is
blocked by the egress policy of the sandbox this parser was written in. The
logic below was tested against fixtures in ``tests/test_core.py`` that were
*written from the format description*, not captured from a real response. It
is structurally sound and completely unverified. When it produces nothing, or
produces nonsense, the fault is here and not in the user's setup, and the
answer is to save one real page to disk, look at it, and fix the parser
against it.

That is also why the parser refuses to key on CSS classes. Class names are the
first thing a redesign changes and the last thing a reader can guess. Instead
it works on the only structure these pages actually share:

    a row is a draw when it contains a date and, after that date, at least six
    distinct integers in 1–90.

Everything else follows from position. Integers *before* the date are contest
numbers, not balls — which is what stops contest 47 being read as the number
47. The first six integers after it are the draw, the seventh is the Jolly,
the eighth is the SuperStar. Cells holding several numbers at once ("1 5 12
33 44 78") tokenise the same way as six separate cells, because the tokeniser
never looks at cell boundaries for anything but ordering.

A row that yields duplicates among its six is dropped rather than repaired.
It means the position assumption broke on that layout, and a plausible-looking
wrong draw in the archive is far more expensive than a missing one.
"""

from __future__ import annotations

import re
from datetime import date

from core.archive import NUMBER_MAX, NUMBER_MIN, NUMBERS_PER_DRAW, ArchiveError, Draw
from core.sources.base import (
    DrawSource,
    ProgressCallback,
    SourceError,
    assign_contest_numbers,
    http_get,
)

# ``{year}`` is substituted per request. Kept as a setting rather than a
# constant because the day this path changes, the fix should not need a
# release — see config/settings.template.json.
DEFAULT_URL_TEMPLATE = "https://www.superenalotto.it/archivio-estrazioni/{year}"

_DATE_PATTERNS = (
    (re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b"), ("d", "m", "y")),
    (re.compile(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b"), ("y", "m", "d")),
)

_INT = re.compile(r"\d+")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


class HtmlTableSource(DrawSource):
    """Per-year HTML archive scrape. Structurally generic, never live-tested."""

    name = "html-archive"

    def __init__(self, url_template: str = DEFAULT_URL_TEMPLATE, years: list[int] | None = None):
        self.url_template = url_template
        self.years = years or []

    def describe(self) -> str:
        return (
            f"HTML archive scrape of {self.url_template} — keeps the archive current, "
            "but has never been run against the live site; verify what it imports."
        )

    def fetch(self, progress: ProgressCallback = None) -> list[Draw]:
        if not self.years:
            raise SourceError("no years requested")
        draws: list[Draw] = []
        failures: list[str] = []
        for i, year in enumerate(sorted(self.years)):
            url = self.url_template.format(year=year)
            self._report(progress, f"Fetching {year}…", i / len(self.years))
            try:
                html = http_get(url).decode("utf-8", errors="replace")
                year_draws = parse_draw_table(html, source=self.name, expect_year=year)
            except SourceError as exc:
                failures.append(f"{year}: {exc}")
                continue
            if not year_draws:
                failures.append(f"{year}: no rows recognised")
            draws.extend(year_draws)
        if not draws:
            raise SourceError(
                "nothing scraped from any requested year — "
                + ("; ".join(failures) if failures else "the page layout has changed")
            )
        if failures:
            print(f"[HtmlTable] partial fetch: {'; '.join(failures)}")
        self._report(progress, f"{len(draws):,} draws scraped.", 1.0)
        return draws


def parse_draw_table(
    html: str, source: str = "html-archive", expect_year: int | None = None
) -> list[Draw]:
    """Extract draws from every ``<tr>`` in the document.

    ``expect_year`` filters out rows from a different year, which the per-year
    pages carry in navigation tables and "last draw" widgets.
    """
    rows: list[dict] = []
    for raw_row in _ROW.findall(html):
        cells = [_text(c) for c in _CELL.findall(raw_row)]
        if not cells:
            continue
        parsed = _row_to_draw_fields(cells)
        if parsed is None:
            continue
        if expect_year is not None and parsed["date"].year != expect_year:
            continue
        rows.append(parsed)

    assign_contest_numbers(rows)
    draws: list[Draw] = []
    for row in rows:
        try:
            draws.append(
                Draw(
                    date=row["date"],
                    contest=row["contest"],
                    numbers=tuple(row["numbers"]),
                    jolly=row["jolly"],
                    superstar=row["superstar"],
                    source=source,
                )
            )
        except ArchiveError as exc:
            print(f"[HtmlTable] dropping implausible row: {exc}")
    return draws


def _text(cell_html: str) -> str:
    """Cell markup to plain text, with tags becoming spaces rather than nothing.

    Stripping ``<span>1</span><span>5</span>`` to ``15`` instead of ``1 5`` is
    exactly how a scraper invents a number that was never drawn, and these
    pages render balls as one element each.
    """
    import html as html_module

    return html_module.unescape(_TAG.sub(" ", cell_html)).strip()


def _find_date(text: str) -> date | None:
    for pattern, order in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parts = dict(zip(order, match.groups(), strict=True))
        try:
            return date(int(parts["y"]), int(parts["m"]), int(parts["d"]))
        except ValueError:
            continue
    return None


def _row_to_draw_fields(cells: list[str]) -> dict | None:
    """Apply the position rules to one row's cell texts, or return None."""
    date_index = None
    draw_date = None
    for i, cell in enumerate(cells):
        found = _find_date(cell)
        if found is not None:
            date_index, draw_date = i, found
            break
    if draw_date is None:
        return None

    # Integers before the date: the contest number, when the page prints one.
    contest = None
    for cell in cells[:date_index]:
        found = _INT.search(cell)
        if found:
            contest = int(found.group())
            break

    # Integers after the date, in reading order. The date cell itself is
    # skipped whole: its own digits are day, month and year, never balls.
    tokens: list[int] = []
    for cell in cells[date_index + 1:]:
        tokens.extend(int(t) for t in _INT.findall(cell))

    balls = [t for t in tokens if NUMBER_MIN <= t <= NUMBER_MAX]
    if len(balls) < NUMBERS_PER_DRAW:
        return None

    numbers = balls[:NUMBERS_PER_DRAW]
    if len(set(numbers)) != NUMBERS_PER_DRAW:
        return None
    rest = balls[NUMBERS_PER_DRAW:]
    return {
        "date": draw_date,
        "contest": contest,
        "numbers": numbers,
        "jolly": rest[0] if rest else 0,
        "superstar": rest[1] if len(rest) > 1 else 0,
    }
