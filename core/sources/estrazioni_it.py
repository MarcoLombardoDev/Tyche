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
same download URL with that value substituted.

It is. Confirmed from CI, which runs on a network that can reach the host:

    158,321 bytes  index.php?p=download&tipo=superenalotto&formato=csv
               first line: DATA;CONCORSO;N1;N2;N3;N4;N5;N6;JOLLY;SUPERSTAR
    parsed 4,260 draws, 1997-12-03 to 2026-09-03

158,321 bytes is byte-for-byte the size of the file the owner downloaded from
the site by hand, so this is that export and not something that resembles it.

The inference is still an inference, and the checks around it stay. ``tipo``
is case-sensitive — ``tipo=superEnalotto`` answers HTTP 500 — which is the
kind of thing that changes silently on somebody else's site. So: several URLs
are tried, the response has to clear a size floor because this kind of CMS
answers a bad query with a 200 and a courtesy page, CI re-checks every
candidate on each dispatch and prints its size and first line, and the GUI
confirms the import even when the preview is clean.

The response is parsed by :func:`core.sources.local_file.parse_any`, so a
downloaded file and a hand-downloaded one go through exactly the same code.
There is no second parser to disagree with the first.
"""

from __future__ import annotations

from core.archive import Draw
from core.localise import it_number
from core.sources.base import DrawSource, ProgressCallback, SourceError, http_get

# Tried in order. All three are confirmed working: the first two are the same
# endpoint with and without ``www``, and the third is a second path the site
# serves the identical file from, kept because a CMS offering two routes may
# retire either one.
#
# A fourth candidate, ``tipo=superEnalotto``, was dropped — it answers HTTP
# 500. The parameter is case-sensitive, which is worth knowing before editing
# this list from memory.
DOWNLOAD_URLS = (
    "https://estrazioni.it/index.php?p=download&tipo=superenalotto&formato=csv",
    "https://www.estrazioni.it/index.php?p=download&tipo=superenalotto&formato=csv",
    "https://estrazioni.it/superenalotto/download.php?formato=csv",
)

# The export is 158,321 bytes as of September 2026. Anything much smaller is
# an error page that happened to return 200, which this kind of site does
# routinely. The floor is an eighth of that: low enough to survive the archive
# shrinking for a reason nobody predicted, high enough to catch a courtesy
# page.
MIN_PLAUSIBLE_BYTES = 20_000


class EstrazioniItSource(DrawSource):
    """One request, the whole archive, current. The best source found so far."""

    name = "estrazioni.it"

    def __init__(self, urls: tuple[str, ...] = DOWNLOAD_URLS):
        self.urls = urls

    def describe(self) -> str:
        return (
            "Esportazione CSV completa da estrazioni.it — una richiesta, dal 1997 "
            "all'ultima estrazione. L'indirizzo di download non è documentato ed è "
            "stato dedotto, perciò la CI lo ricontrolla e l'import va confermato "
            "prima di scrivere."
        )

    def fetch(self, progress: ProgressCallback = None) -> list[Draw]:
        from core.sources.local_file import parse_any

        failures: list[str] = []
        for i, url in enumerate(self.urls):
            self._report(progress, f"Provo {url}…", i / len(self.urls))
            try:
                payload = http_get(url)
            except SourceError as exc:
                failures.append(str(exc))
                continue
            if len(payload) < MIN_PLAUSIBLE_BYTES:
                failures.append(
                    f"{url}: {len(payload)} byte, troppo pochi per essere l'archivio"
                )
                continue
            try:
                draws = parse_any(
                    payload.decode("utf-8-sig", errors="replace"), source=self.name
                )
            except SourceError as exc:
                failures.append(f"{url}: {exc}")
                continue
            self._report(progress, f"{it_number(len(draws))} estrazioni da {url}.", 1.0)
            return draws

        raise SourceError(
            "nessun indirizzo di download ha restituito l'archivio — "
            + "; ".join(failures)
        )
