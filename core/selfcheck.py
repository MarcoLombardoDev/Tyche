# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
selfcheck.py — Tyche

Proves that a built bundle actually works, from inside the bundle.

``--version`` is not a smoke test. argparse prints the version and exits
before anything else is imported, so it establishes that the frozen
interpreter and the bundled standard library are intact and nothing else: a
bundle whose Tcl/Tk libraries were never collected passes it, and so does one
that cannot write a file or import numpy.

This starts Tk for real, reports which windowing system it came up on, builds
the feature matrices, runs the independence tests, and writes and reads back a
file through the program's own persistence code. Each of those is a thing that
has broken in a frozen build of one of these products and in no other
circumstance.

The report goes to a file as well as to stdout, because a ``--windowed``
Windows build has no stdout at all: parsing what it printed would check
nothing on the one platform whose bundle is least like the machine that built
it.
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from datetime import date, timedelta
from pathlib import Path

# Nothing here needs the network, the archive on disk, or the 1.3 GB
# checkpoint. A smoke test that needs any of those is a smoke test that fails
# for reasons having nothing to do with the bundle.


def _check_tk() -> tuple[bool, str]:
    """Start Tk and report the windowing system it came up on.

    The windowing system is the useful part: 'x11', 'aqua' or 'win32' means Tk
    found the real toolkit for the platform. A bundle whose Tcl/Tk data files
    were not collected fails to start at all, which is the failure this
    catches; one that came up on the wrong backend would be stranger still and
    is worth seeing rather than passing over.
    """
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        backend = root.tk.call("tk", "windowingsystem")
        version = root.tk.call("info", "patchlevel")
        root.destroy()
        return True, f"windowing system: {backend}\ntk version: {version}"
    except Exception as exc:
        return False, f"tk: FAILED — {exc}"


def _check_customtkinter() -> tuple[bool, str]:
    """Build one CustomTkinter widget under the real theme.

    CustomTkinter ships its themes and fonts as package data. Without those
    collected the import succeeds and the first widget raises, so importing
    the module is not enough — a widget has to be constructed.
    """
    try:
        import customtkinter as ctk

        from gui.theme import apply_theme

        apply_theme()
        root = ctk.CTk()
        root.withdraw()
        button = ctk.CTkButton(root, text="self-check")
        colour = button.cget("fg_color")
        root.destroy()
        return True, f"customtkinter: {ctk.__version__}, accent {colour}"
    except Exception as exc:
        return False, f"customtkinter: FAILED — {exc}"


def _check_analysis() -> tuple[bool, str]:
    """Run the real analysis over a synthetic archive.

    numpy is the dependency most likely to be missing a compiled extension in
    a frozen build, and it fails at the first matrix rather than at import.
    """
    try:
        import random

        from core.archive import Draw
        from core.features import build_context
        from core.randomness import run_all

        rng = random.Random(0)
        draws = []
        for i in range(400):
            picked = rng.sample(range(1, 91), 7)
            draws.append(Draw(
                date=date(2020, 1, 1) + timedelta(days=2 * i),
                contest=i + 1, numbers=tuple(picked[:6]), jolly=picked[6],
            ))
        context = build_context(draws, context_length=256)
        results = run_all(draws)
        return True, (
            f"analysis: context {context.shape[0]}x{context.shape[1]}, "
            f"{len(results)} independence tests ran"
        )
    except Exception as exc:
        return False, f"analysis: FAILED — {exc}"


def _check_persistence() -> tuple[bool, str]:
    """Write an archive and read it back, through the program's own code.

    Where a frozen build writes its data is decided by
    :func:`core.paths.writable_base_dir`, and getting it wrong means the
    user's archive disappears between runs. This writes into a temporary
    directory rather than beside the executable — a check that leaves files in
    the bundle it is checking has damaged the thing it was protecting — but it
    reports the real base directory so the answer is visible.
    """
    try:
        from core.archive import Draw, load_archive, save_archive
        from core.paths import writable_base_dir

        draw = Draw(date=date(2026, 1, 1), contest=1,
                    numbers=(1, 2, 3, 4, 5, 6), jolly=7, superstar=8)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "selfcheck.csv"
            save_archive(path, [draw])
            back = load_archive(path)
        if len(back) != 1 or back[0].numbers != draw.numbers:
            return False, "persistence: FAILED — the archive did not round-trip"
        return True, f"persistence: ok, data directory would be {writable_base_dir()}"
    except Exception as exc:
        return False, f"persistence: FAILED — {exc}"


def _check_export() -> tuple[bool, str]:
    """Write a SQLite export. sqlite3 is a compiled extension too."""
    try:
        import random

        from core.archive import Draw
        from core.export import export_sqlite

        # Seven numbers sampled, six drawn and the seventh as the Jolly. A
        # fixed Jolly beside six random numbers eventually collides with one
        # of them, and Draw rejects that — correctly, since the real Jolly
        # comes out of the same drum. The first version of this check did
        # exactly that and failed on its own fixture.
        rng = random.Random(1)
        draws = []
        for i in range(10):
            picked = rng.sample(range(1, 91), 7)
            draws.append(Draw(
                date=date(2026, 1, 1) + timedelta(days=i), contest=i + 1,
                numbers=tuple(picked[:6]), jolly=picked[6],
            ))
        with tempfile.TemporaryDirectory() as folder:
            path = export_sqlite(draws, Path(folder) / "selfcheck.db")
            size = path.stat().st_size
        return True, f"sqlite export: ok, {size:,} bytes"
    except Exception as exc:
        return False, f"sqlite export: FAILED — {exc}"


def _check_timesfm() -> tuple[bool, str]:
    """Is TimesFM in the bundle at all?

    Reported, never failed on. The checkpoint is 1.3 GB and lives on Hugging
    Face, so a smoke test cannot run a forecast without turning every build
    into a download; and a bundle without torch is a smaller, working program
    rather than a broken one. What this answers is which of the two was built.
    """
    try:
        import timesfm3  # noqa: F401
        import torch

        return True, f"timesfm: bundled, torch {torch.__version__}"
    except ImportError as exc:
        return True, f"timesfm: not bundled ({exc.name}) — every other method still works"


CHECKS = (
    ("tk", _check_tk),
    ("customtkinter", _check_customtkinter),
    ("analysis", _check_analysis),
    ("persistence", _check_persistence),
    ("sqlite", _check_export),
    ("timesfm", _check_timesfm),
)


def run(report_path: str | None = None) -> int:
    """Run every check. Returns 0 when all of them passed.

    Never raises: a smoke test that crashes tells the caller less than one
    that writes down which check crashed and why.
    """
    from core.version import APP_NAME, __version__

    lines = [f"{APP_NAME} {__version__} self-check", f"frozen: {getattr(sys, 'frozen', False)}"]
    failed = []
    for name, check in CHECKS:
        try:
            ok, message = check()
        except Exception:
            ok, message = False, f"{name}: FAILED — {traceback.format_exc(limit=3)}"
        lines.append(message)
        if not ok:
            failed.append(name)

    lines.append("")
    verdict = "PASSED" if not failed else f"FAILED ({', '.join(failed)})"
    lines.append(f"self-check: {verdict}")
    report = "\n".join(lines)

    print(report)
    if report_path:
        try:
            Path(report_path).write_text(report + "\n", encoding="utf-8")
        except Exception as exc:
            print(f"could not write {report_path}: {exc}")
    return 0 if not failed else 1
