# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
export.py — Tyche

Writes the archive out as SQLite, for querying it with SQL.

**This is an export, not the storage format.** The archive on disk stays CSV,
and the numbers say why. On the 4,260-draw archive:

    CSV      238 KB on disk, 80 ms to load
    SQLite   316 KB on disk,  7 ms to load

SQLite reads eleven times faster, which sounds decisive and is not: the saving
is 73 milliseconds, once, at startup, against a file that is a third larger.
For comparison, building the feature matrices costs 63 ms and running the five
independence tests 52 ms — the CSV load is the same order as work the program
does anyway, and all of it is far below anything a person notices. What CSV
buys in exchange is that the archive greps, diffs in a commit, and opens in a
spreadsheet, which removes an entire class of "what does the file actually
say" question.

What *would* justify moving storage to SQLite, and none of it is true yet:
per-draw prize tiers and payouts (ten times the rows and a second table), a
prediction log that grows without bound, or a genuine need for indexed ad-hoc
queries rather than one full scan.

So this module answers the real want — SQL over the archive — without paying
for it in the storage layer. The database is written fresh each time and is
disposable; nothing in Tyche reads it back.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.archive import Draw
from core.features import counts, current_gaps

SCHEMA = """
CREATE TABLE draws (
    date       TEXT PRIMARY KEY,
    year       INTEGER NOT NULL,
    contest    INTEGER NOT NULL,
    n1 INTEGER, n2 INTEGER, n3 INTEGER,
    n4 INTEGER, n5 INTEGER, n6 INTEGER,
    jolly      INTEGER,
    superstar  INTEGER,
    total      INTEGER NOT NULL,
    source     TEXT
);
CREATE INDEX draws_year ON draws (year);

-- One row per number per draw. Redundant with the six columns above and worth
-- it: "how often did 37 come up in 2024" is a GROUP BY here and a table scan
-- with six OR clauses there. This is the shape that would justify SQLite as
-- the storage format if the program ever needed it at runtime.
CREATE TABLE picks (
    date   TEXT NOT NULL REFERENCES draws (date),
    number INTEGER NOT NULL,
    PRIMARY KEY (date, number)
);
CREATE INDEX picks_number ON picks (number);

-- The frequency table, precomputed, with the expectation beside the count so
-- a query cannot show one without the other.
CREATE TABLE number_stats (
    number    INTEGER PRIMARY KEY,
    times     INTEGER NOT NULL,
    expected  REAL NOT NULL,
    gap       INTEGER NOT NULL
);
"""


def export_sqlite(draws: list[Draw], path: str | Path) -> Path:
    """Write ``draws`` to a fresh SQLite database. Returns the path.

    An existing file at ``path`` is replaced. The database is a snapshot, not
    a store: re-export after updating the archive rather than writing to it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.executemany(
            "INSERT INTO draws VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    d.date.isoformat(), d.year, d.contest, *d.numbers,
                    d.jolly, d.superstar, sum(d.numbers), d.source,
                )
                for d in draws
            ],
        )
        connection.executemany(
            "INSERT INTO picks VALUES (?,?)",
            [(d.date.isoformat(), n) for d in draws for n in d.numbers],
        )
        tally = counts(draws)
        gaps = current_gaps(draws)
        expected = len(draws) * 6 / 90
        connection.executemany(
            "INSERT INTO number_stats VALUES (?,?,?,?)",
            [(n, tally[n], expected, gaps[n]) for n in sorted(tally)],
        )
        connection.commit()
    finally:
        connection.close()
    return path
