# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
streams.py — Tyche

Gives ``sys.stdout`` and ``sys.stderr`` something to write to.

**A windowed build has neither, and that is not a cosmetic problem.**
``Tyche.spec`` passes ``console=False`` on Windows, because a desktop program
should not open a terminal beside its window. PyInstaller then starts the
interpreter with no standard streams at all: ``sys.stdout`` and ``sys.stderr``
are ``None``, not closed files. ``print()`` survives that — CPython checks for
None and does nothing — so the absence stays invisible until some library
writes to the stream itself.

One did. huggingface_hub draws a progress bar on ``sys.stderr`` during a
download, and on the owner's machine pressing «Scarica il modello» answered

    Download di google/timesfm-3.0-pytorch non riuscito:
    'NoneType' object has no attribute 'write'

which reads like a network fault and is not one. It is very probably also what
had been truncating that download for weeks: the bytes were arriving and the
thing drawing the percentage was raising.

So the fix is not "stop that library from printing" — it is to make the
assumption every library is entitled to make true again. Anything written goes
to the null device: a frozen build has nowhere to show it, and a program that
crashes because it could not display a progress bar has its priorities
backwards.
"""

from __future__ import annotations

import os
import sys

# Kept alive deliberately: closing this at the wrong moment would put the
# interpreter back where it started, one library call away from the same
# AttributeError.
_sink = None


def _writable(stream) -> bool:
    """Whether something can be written to without raising."""
    return stream is not None and hasattr(stream, "write")


def ensure_writable_streams() -> list[str]:
    """Replace missing standard streams. Returns the names it had to replace.

    Idempotent, and a no-op everywhere except a windowed frozen build — run
    from source, from a terminal, or under pytest, every stream is already
    there and nothing is touched.

    ``sys.__stdout__`` and ``sys.__stderr__`` are repaired too: a library that
    reaches for the originals rather than the current ones is unusual but not
    rare, and leaving half the job done would make the failure depend on which
    library asked.
    """
    global _sink

    replaced = []
    for name in ("stdout", "stderr", "__stdout__", "__stderr__"):
        if _writable(getattr(sys, name, None)):
            continue
        if _sink is None:
            # Deliberately not a context manager: this file has to outlive
            # the call, for the whole life of the process. ruff's SIM115 is
            # right about almost every other open() and wrong about this one.
            _sink = open(  # noqa: SIM115
                os.devnull, "w", encoding="utf-8", errors="replace"
            )
        setattr(sys, name, _sink)
        replaced.append(name)
    return replaced
