# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
build.py — Tyche

Builds the standalone application:

    pip install -r requirements-build.txt
    python build.py

Produces ``dist/Tyche/`` — a folder holding the executable and everything it
needs. PyInstaller does not cross-compile, so this makes a Windows build on
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
DIST = REPO_ROOT / "dist" / "Tyche"


def _folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


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

    if not DIST.is_dir():
        print(f"[build] PyInstaller reported success but there is nothing at {DIST}.")
        return 1

    executable = DIST / ("Tyche.exe" if sys.platform == "win32" else "Tyche")
    if not executable.exists():
        print(f"[build] no executable at {executable}")
        return 1

    # The launcher belongs beside the executable, in the folder that gets
    # zipped. Copied here rather than declared in the spec: anything the spec
    # adds goes *inside* the bundle's data, where nobody double-clicking the
    # folder would find it.
    launcher = REPO_ROOT / "packaging" / "start.cmd"
    if sys.platform == "win32" and launcher.exists():
        shutil.copy2(launcher, DIST / "start.cmd")
        print(f"[build] launcher: {DIST / 'start.cmd'}")

    print(f"[build] Done: {DIST}  ({_folder_size(DIST) / (1024 * 1024):.0f} MB)")
    print("[build] Copy the whole folder — it creates its own data/ and config/ inside it.")
    print("[build] Check it with:  Tyche --self-check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
