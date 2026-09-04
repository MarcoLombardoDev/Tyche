# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
core.sources — where draw history comes from.

Four sources, deliberately different in kind, listed here by how much they
should be trusted:

- :mod:`core.sources.local_file` imports whatever the user downloaded by
  hand. It cannot break, it needs no network, and it is where the archive on
  disk came from — a CSV export the owner downloaded and passed to
  ``--import``.
- :mod:`core.sources.estrazioni_it` fetches that same export automatically.
  Same file, same parser, no manual step; its download URL is inferred rather
  than documented, so CI checks it and the import is confirmed before it
  writes.
- :mod:`core.sources.bulk_archive` downloads a mirrored historical CSV. It
  needs no configuration and it is stale — the mirror was last refreshed in
  January 2020 — and it disagrees with the export about twelve draws. A
  bootstrap, not a source of truth.
- :mod:`core.sources.html_table` scrapes a per-year archive page. The last
  resort, and the only one that has never parsed a live page — see the
  parser's own docstring before trusting it.

They all return ``list[Draw]`` and nothing else, so the merge in
:mod:`core.archive` does not care which one produced a row.
"""

from core.sources.base import DrawSource, SourceError
from core.sources.bulk_archive import BulkArchiveSource
from core.sources.estrazioni_it import EstrazioniItSource
from core.sources.html_table import HtmlTableSource
from core.sources.local_file import LocalFileSource

__all__ = [
    "BulkArchiveSource",
    "DrawSource",
    "EstrazioniItSource",
    "HtmlTableSource",
    "LocalFileSource",
    "SourceError",
]
