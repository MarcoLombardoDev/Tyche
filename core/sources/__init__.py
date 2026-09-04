# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
core.sources — where draw history comes from.

Three sources, deliberately different in kind, because no single one of them
is both current and verifiable:

- :mod:`core.sources.bulk_archive` downloads the mirrored historical CSV. It
  is the only source this code has ever been run against end to end, and it
  is also the one that stops being current: the mirror it reads was last
  refreshed in 2020. It bootstraps an archive; it cannot maintain one.
- :mod:`core.sources.html_table` scrapes a per-year archive page. This is the
  source that keeps the archive current, and it is the one nobody has been
  able to run against the live site from inside a sandbox — see the parser's
  own docstring before trusting it.
- :mod:`core.sources.local_file` imports whatever the user downloaded by
  hand. It is the fallback that cannot break, and the reason a scraper
  failure is an inconvenience rather than a dead end.

They all return ``list[Draw]`` and nothing else, so the merge in
:mod:`core.archive` does not care which one produced a row.
"""

from core.sources.base import DrawSource, SourceError
from core.sources.bulk_archive import BulkArchiveSource
from core.sources.html_table import HtmlTableSource
from core.sources.local_file import LocalFileSource

__all__ = [
    "BulkArchiveSource",
    "DrawSource",
    "HtmlTableSource",
    "LocalFileSource",
    "SourceError",
]
