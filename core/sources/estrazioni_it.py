# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
estrazioni_it.py — Tyche

Downloads the whole archive as a CSV from estrazioni.it, in one request.

This is the source Tyche's archive actually came from — by hand, at first: the
owner downloaded the export and passed it to ``--import``. It is worth having
as a source because that file is the best one anybody has found. 4,260 draws
from 3 December 1997 to the day before yesterday, a labelled header, and zero
integrity issues against :func:`core.archive.integrity_report`, where the bulk
mirror has fourteen.

**How the URL was found, since it is not published anywhere.** The site's
SuperEnalotto page carries a download link reading
``/index.php?p=download&tipo=lotto&formato=csv`` — the *Lotto* export, on the
SuperEnalotto page, which is either a static navigation link or a leftover.
The page's own address is ``index.php?p=home&anno=2026&tipo=superenalotto``,
so ``tipo`` is the game selector and the SuperEnalotto export should be the
same download URL with the same value substituted. That is an inference from
two observed URLs rather than documentation, which is why several spellings
are tried and why CI fetches the file and counts the rows: a guess nobody
checks is a guess that fails in front of the user.

The response is parsed by :func:`core.sources.local_file.parse_any`, so a
downloaded file and a hand-downloaded one go through exactly the same code.
There is no second parser to disagree with the first.
"""

from __future__ import annotations

from core.archive import Draw
from core.sources.base import DrawSource, ProgressCallback, SourceError, http_get

# Tried in order. The first is the inference above; the rest cover the
# spellings the same page could plausibly be using.
DOWNLOAD_URLS = (
    "https://estrazioni.it/index.php?p=download&tipo=superenalotto&formato=csv",
    "https://www.estrazioni.it/index.php?p=download&tipo=superenalotto&formato=csv",
    "https://estrazioni.it/index.php?p=download&tipo=superEnalotto&formato=csv",
    "https://estrazioni.it/superenalotto/download.php?formato=csv",
)

# The export is around 160 KB. Anything much smaller is an error page that
# happened to return 200, which this kind of site does routinely.
MIN_PLAUSIBLE_BYTES = 20_000


class EstrazioniItSource(DrawSource):
    """One request, the whole archive, current. The best source found so far."""

    name = "estrazioni.it"

    def __init__(self, urls: tuple[str, ...] = DOWNLOAD_URLS):
        self.urls = urls

    def describe(self) -> str:
        return (
            "Full CSV export from estrazioni.it — one request, 1997 to the last "
            "draw. The download URL is inferred rather than documented, so the "
            "import is confirmed before anything is written."
        )

    def fetch(self, progress: ProgressCallback = None) -> list[Draw]:
        from core.sources.local_file import parse_any

        failures: list[str] = []
        for i, url in enumerate(self.urls):
            self._report(progress, f"Trying {url}…", i / len(self.urls))
            try:
                payload = http_get(url)
            except SourceError as exc:
                failures.append(str(exc))
                continue
            if len(payload) < MIN_PLAUSIBLE_BYTES:
                failures.append(f"{url}: {len(payload)} bytes, too small to be the archive")
                continue
            try:
                draws = parse_any(
                    payload.decode("utf-8-sig", errors="replace"), source=self.name
                )
            except SourceError as exc:
                failures.append(f"{url}: {exc}")
                continue
            self._report(progress, f"{len(draws):,} draws from {url}.", 1.0)
            return draws

        raise SourceError("no download URL returned the archive — " + "; ".join(failures))
