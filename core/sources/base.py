# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
base.py — Tyche

The interface every draw source implements, and the shared plumbing that
would otherwise be copy-pasted three times.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from core.archive import Draw
from core.version import __version__

# A source that hangs is worse than a source that fails: the GUI runs fetches
# on a worker thread and the user cannot tell the two apart.
DEFAULT_TIMEOUT = 30

# Sent on every outbound request, and deliberately honest.
#
# The first version of this claimed to be Chrome, on the usual assumption that
# a browser string gets through where a script does not. It gets *fewer*
# things: SourceForge answers the Chrome string with a 403 and the same
# request with ``curl/8.5.0`` or a plain ``python-requests`` with a 200,
# because a browser user agent arriving without any of the headers a browser
# also sends is a better bot signature than admitting to being a bot. Saying
# what this is costs nothing and names the traffic for whoever reads the logs.
# Built from __version__ rather than typed out: the literal that used to be
# here still said 0.1.0 after the first version bump, which is the failure
# mode of every hardcoded version string.
USER_AGENT = f"Tyche/{__version__} (SuperEnalotto archive importer)"

# Sent alongside it. ``requests`` omits Accept entirely by default, and some
# CDNs treat that as a signature too.
ACCEPT = "*/*"

ProgressCallback = Callable[[str, float], None] | None


class SourceError(RuntimeError):
    """A source could not produce draws: network, HTTP status, or parse."""


class DrawSource(ABC):
    """Something that can produce a list of :class:`~core.archive.Draw`.

    Sources are intentionally dumb. They do not deduplicate, they do not know
    what is already on disk, and they do not decide what is current — the
    caller merges what they return into the archive. Keeping that logic in one
    place is what lets a badly behaved source be swapped out without touching
    the merge rules.
    """

    #: Written into the ``source`` column of every row the source produces, so
    #: a suspect row can be traced back to where it came from.
    name: str = "unknown"

    @abstractmethod
    def fetch(self, progress: ProgressCallback = None) -> list[Draw]:
        """Return every draw this source knows about. May raise SourceError."""

    def describe(self) -> str:
        """One line for the GUI, saying what this source is and its limits."""
        return self.name

    @staticmethod
    def _report(progress: ProgressCallback, message: str, fraction: float) -> None:
        if progress:
            progress(message, fraction)


def http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    """GET a URL, following redirects, raising :class:`SourceError` on failure.

    Wrapped rather than called directly so that every source reports a network
    problem the same way, and so ``requests`` is imported in exactly one place
    if it ever needs replacing.
    """
    import requests

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": ACCEPT},
            allow_redirects=True,
        )
    except Exception as exc:  # requests raises a family, all equally fatal here
        raise SourceError(f"{url}: {_reason(exc)}") from exc
    if response.status_code != 200:
        raise SourceError(f"{url}: HTTP {response.status_code}")
    return response.content


def _reason(exc: Exception) -> str:
    """A requests exception as one short clause.

    ``str()`` on a ``requests`` connection error is three nested exceptions and
    about 250 characters, most of it the URL again. The scraper tries four
    hosts and reports every failure, so the untruncated version produces a
    thousand-character sentence that nobody reads to the end — and the useful
    part, "the host could not be reached", was in the first four words. The
    original is still chained for anyone with a debugger.
    """
    name = type(exc).__name__
    if "Proxy" in name:
        return "blocked or unreachable through the proxy"
    if "Timeout" in name:
        return "timed out"
    if "SSL" in name:
        return "TLS verification failed"
    if "ConnectionError" in name:
        return "could not connect"
    text = str(exc).splitlines()[0] if str(exc) else name
    return text if len(text) <= 120 else f"{text[:117]}…"


def assign_contest_numbers(rows: list[dict]) -> list[dict]:
    """Fill in a missing contest number as the draw's ordinal within its year.

    Some archive pages print the contest number and some only print the date.
    The number restarts at 1 each January and increments by one per draw, so
    for a source that returns a complete year the ordinal *is* the contest
    number. For a partial year it is a guess, and a wrong one — which is why
    this is only ever applied to whole-year fetches, and why a source that
    publishes the real number must pass it through instead.
    """
    by_year: dict[int, int] = {}
    for row in sorted(rows, key=lambda r: r["date"]):
        year = row["date"].year
        by_year[year] = by_year.get(year, 0) + 1
        if not row.get("contest"):
            row["contest"] = by_year[year]
    return rows
