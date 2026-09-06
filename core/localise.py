# Tyche — Analisi dell'archivio SuperEnalotto e previsioni con TimesFM
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
localise.py — Tyche

Numbers and dates as an Italian reader expects them, in one place.

Tyche's entire audience plays an Italian game, so the interface is Italian and
so is everything it prints. Two conventions differ from the defaults Python
hands out, and both are the kind of thing that gets fixed in four places and
missed in the fifth:

- **thousands are separated with a full stop**, so ``622.614.630`` and not
  ``622,614,630``. Python's ``{:,}`` gives the English form.
- **dates are day-first**, so ``03/09/2026`` and not ``2026-09-03``.

**Presentation only.** The archive on disk keeps ISO dates and bare integers.
Those sort lexicographically, are unambiguous to every tool that will ever
open the CSV, and are what a second source will be compared against;
localising storage is how an archive becomes unsortable and a merge starts
depending on the reader's locale.

Decimals keep the full stop rather than taking the Italian comma. That is a
deliberate exception and the alternative is worse: the statistics on screen
are χ² values, z scores and p-values sitting beside counts, and switching the
separator would mean either converting every one of them or printing ``0,400``
next to ``13.95`` in the same line. Scientific output in Italian is routinely
written with the point, and one convention consistently applied beats two
applied by hand.
"""

from __future__ import annotations

from datetime import date


def it_number(value: int | float, decimals: int = 0) -> str:
    """``1234567`` as ``1.234.567``.

    Built by formatting with the English separators and swapping them, which
    is the trick that avoids depending on a system locale being installed —
    ``it_IT.UTF-8`` is present on the developer's machine and absent from
    every CI runner this project uses.
    """
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def it_date(value: date | None, empty: str = "—") -> str:
    """``date(2026, 9, 3)`` as ``03/09/2026``."""
    return value.strftime("%d/%m/%Y") if value else empty


def it_count(value: int, singular: str, plural: str) -> str:
    """``1 estrazione`` / ``4.260 estrazioni``, with the number localised.

    Italian agreement is not optional the way English's often is, and "1
    estrazioni" in an interface reads as a bug in everything around it.
    """
    return f"{it_number(value)} {singular if value == 1 else plural}"
