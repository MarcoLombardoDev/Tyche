# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
bulk_archive.py — Tyche

Bootstraps the archive from the mirrored ``EnalStorico.CSV``, the bulk history
file that has been passed around Italian lottery hobbyist sites for two
decades. One request, the whole history, no scraping.

**It stops in January 2020.** The mirror is not maintained; the last row in
the copy this parser was written against is contest 2020/9, drawn on the 21st
of January. That is not a bug to work around, it is what the source is: a
bootstrap that saves the user importing twenty-two years of history by hand,
followed by an HTML scrape or a manual import for everything since. Treating
it as the live source is the mistake this docstring exists to prevent.

The format is twelve unlabelled comma-separated columns and no header:

    n1,n2,n3,n4,n5,n6,jolly,superstar,contest,day,month,year

Two properties of it were checked against the real file rather than assumed,
because both are load-bearing for :meth:`core.archive.Draw.validate`:

- the Jolly never repeats one of the six main numbers, in any of the 5,038
  rows — so rejecting a row where it does really is a mis-parse and not a
  quirk of the game;
- the SuperStar *does* repeat a main number, in 163 rows, because it comes
  from a separate drum. A validator that rejected those would throw away four
  years of data.

Rows are quoted in some revisions of the file and bare in others, sometimes
with leading zeros (``"08"``); ``csv`` plus ``int()`` handles both. Rows
before 3 December 1997 are Enalotto, and :func:`core.archive.superenalotto_only`
drops them — 5,038 rows in, about 3,076 out. One further row is unparseable
in every copy seen so far: an Enalotto draw dated 29 February 1991, a date
that did not exist. It is skipped and it is outside the SuperEnalotto era
anyway.

The file is also wrong in a way no per-row check can see: the first nine
draws of 1999 are labelled 1998, giving nine duplicated contest ids and two
pairs of different draws sharing a date. :func:`core.archive.repair_year_offset`
puts them back, and this source applies it on import — an archive that is
known-wrong on disk gets analysed as if it were right.
"""

from __future__ import annotations

import csv
import io

from core.archive import Draw, repair_year_offset, superenalotto_only
from core.sources.base import DrawSource, ProgressCallback, SourceError, http_get

# The SourceForge project's own download host. ``sourceforge.net/projects/...``
# serves an interstitial HTML page rather than the file; ``downloads.`` is the
# one that redirects straight to a mirror and returns the bytes.
DEFAULT_URL = "https://downloads.sourceforge.net/project/superenalotto/EnalStorico.CSV"

EXPECTED_COLUMNS = 12


class BulkArchiveSource(DrawSource):
    """One-shot historical bootstrap. Current only up to January 2020."""

    name = "bulk-archive"

    def __init__(self, url: str = DEFAULT_URL):
        self.url = url

    def describe(self) -> str:
        return (
            "Bulk historical CSV (1961→2020-01). Bootstrap only — this mirror "
            "is no longer updated; refresh recent draws from another source."
        )

    def fetch(self, progress: ProgressCallback = None) -> list[Draw]:
        self._report(progress, f"Downloading {self.url}…", 0.1)
        payload = http_get(self.url)
        self._report(progress, f"Parsing {len(payload):,} bytes…", 0.6)
        draws = parse_bulk_csv(payload.decode("utf-8", errors="replace"), source=self.name)
        kept = superenalotto_only(draws)
        # Order matters twice over: the pre-1997 filter preserves file order,
        # which the repair needs, and the repair must not see the Enalotto
        # rows, whose contest numbering is a separate sequence.
        kept, notes = repair_year_offset(kept)
        for note in notes:
            print(f"[BulkArchive] {note}")
        self._report(
            progress,
            f"{len(kept):,} SuperEnalotto draws ({len(draws) - len(kept):,} pre-1997 rows dropped, "
            f"{len(notes)} label repairs).",
            1.0,
        )
        return kept


def parse_bulk_csv(text: str, source: str = "bulk-archive") -> list[Draw]:
    """Parse the twelve-column bulk format. Raises SourceError if nothing parses.

    Individual bad rows are skipped rather than fatal — a single corrupt line
    in a five-thousand-row file should not cost the user the other 5,037 — but
    a file where *nothing* parses is a different failure: it means the URL now
    serves an error page, and silently returning an empty list would look like
    "no new draws" to the caller.
    """
    from datetime import date

    draws: list[Draw] = []
    skipped = 0
    for fields in csv.reader(io.StringIO(text)):
        if len(fields) < EXPECTED_COLUMNS:
            skipped += 1
            continue
        try:
            numbers = tuple(int(fields[i]) for i in range(6))
            draws.append(
                Draw(
                    date=date(int(fields[11]), int(fields[10]), int(fields[9])),
                    contest=int(fields[8]),
                    numbers=numbers,
                    jolly=int(fields[6]),
                    superstar=int(fields[7]),
                    source=source,
                )
            )
        except Exception:
            skipped += 1
    if not draws:
        raise SourceError(
            f"no draws parsed from {len(text):,} characters — the URL is probably "
            f"serving an error page rather than the CSV ({skipped} unusable rows)"
        )
    if skipped:
        print(f"[BulkArchive] skipped {skipped} unusable rows")
    return draws
