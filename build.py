# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
build.py — Tyche

Builds the standalone application:

    pip install -r requirements-build.txt
    python build.py

Produces ``dist/Tyche`` — one executable with everything inside it, which
unpacks itself to a temporary folder on each launch. PyInstaller does not
cross-compile, so this makes a Windows build on
Windows and nothing else: the release workflow runs it on a windows-latest
runner, which is the only way to get a genuine .exe without owning a Windows
machine.

Not part of the test suite or any test job. Run it when you want a bundle.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SPEC = REPO_ROOT / "Tyche.spec"
#: What the build produces: one file, named for the platform that runs it.
#: This was ``dist/Tyche`` as a *directory* until 1.3.0, and the check below
#: still said ``is_dir()`` on the first release of the onefile build — so
#: PyInstaller finished on all three runners, wrote the executable, and this
#: script reported that there was nothing there.
EXECUTABLE = REPO_ROOT / "dist" / ("Tyche.exe" if sys.platform == "win32" else "Tyche")


def main() -> int:
    if importlib.util.find_spec("PyInstaller") is None:
        print("[build] PyInstaller not found — installing it "
              "(pip install -r requirements-build.txt)…")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements-build.txt"],
            cwd=REPO_ROOT, check=True,
        )

    # --clean rather than trusting the cache: a stale build/ directory from a
    # spec that collected different packages produces a bundle nobody can
    # reason about, and the failure appears as a missing module at runtime.
    print(f"[build] Running PyInstaller against {SPEC.name}…")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print("[build] PyInstaller failed — see the output above.")
        return result.returncode

    if not EXECUTABLE.is_file():
        print(f"[build] PyInstaller reported success but there is nothing at {EXECUTABLE}.")
        return 1

    # The launcher belongs beside the executable, not inside the bundle:
    # anything the spec declares as data is packed into the executable and
    # unpacked to a temporary directory while the program runs, where nobody
    # would ever find it.
    launcher = REPO_ROOT / "packaging" / "start.cmd"
    if sys.platform == "win32" and launcher.exists():
        beside = EXECUTABLE.parent / "start.cmd"
        shutil.copy2(launcher, beside)
        print(f"[build] launcher: {beside}")

    size = EXECUTABLE.stat().st_size / (1024 * 1024)
    print(f"[build] Done: {EXECUTABLE}  ({size:.0f} MB)")
    print("[build] One file. It creates its own data/ and config/ beside itself,")
    print("[build] so put it where you want those to live.")
    print("[build] Check it with:  Tyche --self-check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
