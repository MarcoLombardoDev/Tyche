# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
paths.py — Tyche

Resolves the one directory every persistence path in the app is built from:
where should ``.env``, ``config/settings.json`` and ``data/`` live?

Running from source, "next to the code" and "the project root" are the same
place, so ``Path(__file__).resolve().parent.parent`` used to answer both
questions at once. They stop being the same place the moment the app is
frozen into a single executable with PyInstaller: a ``--onefile`` build
unpacks itself into a fresh temporary directory (``sys._MEIPASS``) on every
launch and deletes it on exit, and a module's ``__file__`` inside that bundle
resolves *into that temp directory*. Anything written there — settings, the
draw archive, saved predictions — would silently disappear the
moment the user closes the app.

``writable_base_dir()`` is the single place that tells the two cases apart,
so every module that persists data imports it instead of recomputing
``Path(__file__).resolve().parent.parent`` on its own.
"""

import sys
from pathlib import Path


def writable_base_dir() -> Path:
    """Directory where user data must persist across runs.

    - Frozen (PyInstaller): next to the executable itself, so a onefile
      build stays portable — copy the .exe anywhere and its data folder
      travels with it.
    - Running from source: the repository root, same as before.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_dir() -> Path:
    """Directory holding files that ship with the program and are never
    written to — the icon, and anything else added to the bundle.

    The mirror image of :func:`writable_base_dir`, and deliberately a
    different answer. A onefile build unpacks its read-only payload into
    ``sys._MEIPASS`` and deletes it on exit, which is exactly where data that
    must survive the run must not go, and exactly where a bundled resource
    is. Confusing the two costs the user their settings one way and gives
    them a missing icon the other.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent
