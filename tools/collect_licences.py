#!/usr/bin/env python
# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""Assemble the licence texts that must travel inside a release archive.

Every archive Tyche published up to 0.3.3 contained the program and no licence
file at all — not even Tyche's own. A recursive search of the folder for
LICENSE, COPYING or NOTICE returned nothing. That is not a formality: PyTorch,
NumPy and the rest of the BSD and MIT libraries frozen into that folder require
their copyright notices be reproduced in binary distributions, the LGPL-2.1
system libraries PyInstaller collects on Linux require a copy of their licence
to accompany the object code, and Tyche's own AGPL requires the same. Shipping
a hundred-odd libraries with none of their terms attached is a straightforward
compliance defect, and THIRD-PARTY-LICENSES.md sitting in the repository does
not fix it — somebody who downloads a zip never sees it.

Tyche is a folder build, so the tree this produces goes *inside* it, at
``licenses/`` beside the executable, where opening the archive is enough to
find it. Argus is ``--onefile`` and has to package the same tree beside its
binary instead, because anything added to a onefile bundle is sealed inside the
executable and visible only to somebody who has already run it. The two scripts
are otherwise the same, deliberately.

Run after the build rather than from the .spec file: what to collect is read
out of PyInstaller's own record of what it collected, and that record does not
exist until Analysis has run.

Three sources feed it, in descending order of authority:

1. **The distributions themselves.** Most wheels ship their licence in
   dist-info, and that copy is the one their authors chose to send. Pillow's is
   worth having in particular: it covers every native library Pillow vendors,
   from libjpeg to zstd, and none of those has a wheel of its own to ask.

2. **Canonical texts vendored in ``licenses/``**, for the parts of the runtime
   that are not Python distributions at all and so have no metadata to read:
   CPython, whose interpreter and standard library are frozen into the
   executable, and Tcl/Tk, whose shared libraries arrive with tkinter. Neither
   is a wheel; both are in every archive. ``SUPPLIED_TEXTS`` covers the related
   case of a wheel that declares a licence and then ships no copy of it.

3. **The build machine's package copyright records**, on Linux, for the
   libraries PyInstaller collected from the system. These vary with the runner
   image, which is exactly why they are read at build time rather than
   committed.

Which distributions to collect is *not* a list kept here by hand. A list like
that is right on the day it is written and wrong the first time a dependency
grows a dependency of its own — the one failure mode where being wrong looks
exactly like being right. It is read instead out of PyInstaller's own record of
what it collected, so it describes the archive being built rather than the
requirements file somebody last edited.

    python tools/collect_licences.py build/licenses
"""

from __future__ import annotations

import ast
import logging
import os
import re
import shutil
import subprocess
import sys

log = logging.getLogger(__name__)

APP_NAME = "Tyche"

#: Distributions whose wheels declare a licence and ship no copy of it, mapped
#: to the canonical texts supplied on their behalf from ``licenses/``.
SUPPLIED_TEXTS: dict[str, tuple[str, ...]] = {}

#: Texts that belong in every archive and that no distribution owns: the
#: interpreter frozen into the bundle, and the toolkit tkinter binds to.
#: Tcl's terms and Tk's are the same permissive licence but not the same file —
#: they name different copyright holders and cite different DFARs clauses — so
#: both travel rather than one standing in for the other. The interpreter's
#: folder is `cpython/` and not `python/` because `python/` is where the
#: wheels go, and the two collided.
ALWAYS_SUPPLIED = (
    ("cpython", "Python-LICENSE.txt", "CPython — the interpreter and standard library"),
    ("tcl-tk", "Tcl-license.terms.txt", "Tcl"),
    ("tcl-tk", "Tk-license.terms.txt", "Tk"),
)

#: Distributions that are never in the archive however they were installed.
#: PyInstaller is deliberately *not* among them: its bootloader is the
#: executable this bundle starts from, under an exception that permits exactly
#: that, so its COPYING.txt comes along.
BUILD_ONLY = {"pip", "setuptools", "wheel", "altgraph", "pyinstaller-hooks-contrib"}

#: Texts for libraries the *platform* supplies rather than a package manager,
#: and that no wheel carries either. On Linux these arrive as dpkg copyright
#: records; on Windows and macOS nothing names them, and an archive without
#: this would ship zlib and LibTomMath with no notice at all. Both come with
#: Tcl 9 rather than by anyone asking for them.
PLATFORM_TEXTS = (
    ("Zlib.txt", "zlib, which Tcl links"),
    ("LibTomMath.txt", "LibTomMath, which Tcl 9 uses for bignums"),
)

#: A licence file is usually *named* like one...
LICENCE_FILE = re.compile(r"(?i)^(licen[cs]e|copying|notice|authors)")

#: ...but not always. Some wheels name their files after the licence rather
#: than after the word — Apache-2.0.txt, BSD-3-Clause.txt, one per library they
#: vendor. Matching on the file name alone collected none of those, silently,
#: which is precisely the failure this script exists to prevent; so a file
#: sitting in a directory that announces itself as licences counts too.
LICENCE_DIRECTORY = re.compile(r"(?i)^(licen[cs]es?|build_licenses)$")


def _analysis_toc(repo: str):
    """PyInstaller's record of what it collected, or ``None``.

    ``build/<app>/Analysis-00.toc`` is a repr of Python objects that
    PyInstaller writes for its own use. Read with ``ast.literal_eval`` rather
    than ``eval``: the file is generated rather than typed, but nothing here
    needs the power to execute it.
    """
    path = os.path.join(repo, "build", APP_NAME, "Analysis-00.toc")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return ast.literal_eval(handle.read())
    except (OSError, SyntaxError, ValueError):
        log.warning("Could not read %s", path, exc_info=True)
        return None


def _entries(parsed, *typecodes: str) -> list[tuple[str, str]]:
    """``(destination, source)`` for the TOC entries of the given typecodes."""
    found = []
    for section in parsed or ():
        if not isinstance(section, list):
            continue
        for entry in section:
            if (isinstance(entry, tuple) and len(entry) == 3
                    and entry[2] in typecodes):
                found.append((str(entry[0]), str(entry[1])))
    return found


def shipped_distributions(repo: str) -> list[str]:
    """Which installed distributions put something in the bundle.

    Every Python module and extension PyInstaller collected is traced back to
    the distribution that owns its top-level package. That catches transitive
    dependencies nobody wrote down — a wheel pulled in by a wheel — which is
    exactly the class this has to get right, since those are the ones a
    hand-kept list misses.

    Falls back to every installed distribution when there is no build to read,
    so running this without building first over-collects rather than
    under-collects. A licence text too many is noise; one too few is the defect.
    """
    from importlib.metadata import distributions, packages_distributions

    owners = packages_distributions()
    parsed = _analysis_toc(repo)
    if parsed is None:
        log.warning("No PyInstaller build found under %s; collecting everything "
                    "installed", repo)
        names = {dist.metadata["Name"] for dist in distributions()
                 if dist.metadata["Name"]}
    else:
        names = set()
        for destination, _source in _entries(parsed, "PYMODULE", "EXTENSION"):
            top = destination.replace("\\", "/").split("/")[0].split(".")[0]
            names.update(owners.get(top, ()))
        # The bootloader is not a Python module, so nothing above finds it.
        names.add("pyinstaller")
    return sorted(
        (name for name in names if name.lower() not in BUILD_ONLY),
        key=str.lower,
    )


def _distribution_licence_files(name: str) -> list[tuple[str, str]]:
    """Return ``(relative path, text)`` for every licence file a wheel ships.

    The path is kept relative to the dist-info directory rather than reduced to
    a bare file name. Wheels put licence files in both places — ``LICENSE``
    beside METADATA and ``licenses/LICENSE`` below it — and some ship twenty of
    them, one per vendored package, all named LICENSE. Writing by base name
    would have each overwrite the last and leave a tree that looks complete and
    is not, which is the one outcome this script exists to prevent.
    """
    from importlib.metadata import distribution

    try:
        dist = distribution(name)
    except Exception:
        return []
    found = []
    for file in dist.files or ():
        parts = str(file).split("/")
        info = next(
            (i for i, part in enumerate(parts)
             if part.endswith((".dist-info", ".egg-info"))),
            None,
        )
        if info is None:
            continue
        below = parts[info + 1:]
        named = LICENCE_FILE.match(parts[-1])
        housed = any(LICENCE_DIRECTORY.match(part) for part in below[:-1])
        if not named and not housed:
            continue
        try:
            text = _read_text(file.locate())
        except Exception:
            # Loud on purpose. A licence file that cannot be read has to be
            # noticed, not quietly left out of the archive — a tree that looks
            # complete and is not is worse than one with an obvious hole.
            log.warning("Could not read the licence file %s", file, exc_info=True)
            continue
        found.append(("/".join(below), text))
    return _flatten(found)


def _read_text(path) -> str:
    """Read a licence file whatever it happens to be encoded in.

    Not everything is UTF-8. Several of the older notices that arrive vendored
    inside wheels are Latin-1: the copyright sign is a single byte there, UTF-8
    rejects it outright, the exception handler above drops the file, and the
    tree comes out one notice short with nothing to say so.

    Latin-1 is the fallback because it cannot fail — every byte is a character
    — and it decodes exactly the Western European text these older files
    contain. The result is written back out as UTF-8.
    """
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _flatten(files: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop the leading ``licenses/`` most wheels wrap their texts in.

    It is a packaging convention, not information, and keeping it produces
    licenses/python/pillow/licenses/LICENSE. Dropped only where it does not
    collide with a file already sitting at the top of dist-info — a wheel that
    ships both LICENSE and licenses/LICENSE keeps them apart.
    """
    names = {path for path, _ in files}
    flattened = []
    for path, text in files:
        head, _, rest = path.partition("/")
        if head == "licenses" and rest and rest not in names:
            path = rest
        flattened.append((path, text))
    return flattened


def _system_packages(repo: str) -> list[str]:
    """Package names owning the system libraries PyInstaller collected.

    Only meaningful on a Debian-family build machine. Everywhere else this
    returns nothing and the caller records why.
    """
    if not shutil.which("dpkg-query"):
        return []
    packages = set()
    for _destination, source in _entries(_analysis_toc(repo), "BINARY"):
        # Wheel-vendored libraries live under site-packages; only the ones
        # taken from the system's own lib directories have an owning package.
        if "site-packages" in source or not os.path.exists(source):
            continue
        found = subprocess.run(
            ["dpkg-query", "-S", os.path.realpath(source)],
            capture_output=True,
            text=True,
        )
        if found.returncode == 0 and found.stdout.strip():
            packages.add(found.stdout.split(":")[0].strip())
    return sorted(packages)


def collect(repo: str, staging: str) -> str:
    """Build the licence tree under ``staging`` and return its path."""
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)

    index = [
        "# Licences of the software in this package",
        "",
        "Tyche itself is licensed AGPL-3.0-or-later; the full text is in",
        "`Tyche-LICENSE.txt`. That is the only licence it is offered under.",
        "",
        "The TimesFM model weights are a separate matter and are not in this",
        "package: Tyche downloads them from Hugging Face on first use, and the",
        "3.0 checkpoint it defaults to declares",
        "`timesfm-non-commercial-license-v1.0` — non-commercial and",
        "non-production use. That permission is not Tyche's to give, and it is",
        "not given here. The `timesfm` package code around the weights is",
        "Apache-2.0 and is in this package like any other dependency.",
        "",
        "Everything else in this package was written by other people, under",
        "their own terms. This directory holds those terms. The inventory of",
        "which binary belongs to which project, and what each licence requires",
        "of somebody redistributing it, is THIRD-PARTY-LICENSES.md in the",
        "Tyche repository.",
        "",
        "## Tyche",
        "",
        "- `Tyche-LICENSE.txt` — GNU Affero General Public License v3.0",
        "",
    ]

    shutil.copyfile(
        os.path.join(repo, "LICENSE"), os.path.join(staging, "Tyche-LICENSE.txt")
    )

    index += ["## The interpreter and the toolkit", ""]
    for folder, canonical, description in ALWAYS_SUPPLIED:
        target = os.path.join(staging, folder)
        os.makedirs(target, exist_ok=True)
        shutil.copyfile(
            os.path.join(repo, "licenses", canonical),
            os.path.join(target, canonical),
        )
        index.append(f"- **{description}** — `{folder}/{canonical}`")
    index.append("")

    index += ["## Python packages", ""]
    python_dir = os.path.join(staging, "python")
    os.makedirs(python_dir)
    for name in shipped_distributions(repo):
        files = _distribution_licence_files(name)
        supplied = SUPPLIED_TEXTS.get(name, ())
        if not files and not supplied:
            # Recorded rather than passed over: a gap somebody can see is worth
            # more than a tree that looks complete and is not.
            index.append(f"- **{name}** — no licence file found; see the inventory")
            continue
        target = os.path.join(python_dir, name)
        os.makedirs(target, exist_ok=True)
        written = []
        for filename, text in files:
            destination = os.path.join(target, *filename.split("/"))
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "w", encoding="utf-8") as out:
                out.write(text)
            written.append(filename)
        for canonical in supplied:
            shutil.copyfile(
                os.path.join(repo, "licenses", canonical),
                os.path.join(target, canonical),
            )
            written.append(f"{canonical} (supplied — the wheel ships none)")
        index.append(f"- **{name}** — {', '.join(written)}")
    index.append("")

    packages = _system_packages(repo)
    index += ["## System libraries collected at build time", ""]
    if packages:
        system_dir = os.path.join(staging, "system")
        os.makedirs(system_dir)
        for package in packages:
            source = f"/usr/share/doc/{package.split(':')[0]}/copyright"
            if not os.path.exists(source):
                continue
            shutil.copyfile(source, os.path.join(system_dir, f"{package}.txt"))
        index.append(
            f"The build machine's copyright records for {len(packages)} packages "
            "are in `system/`, one file per package, exactly as that machine "
            "stated them."
        )
    else:
        index.append(
            "This build was not produced on a Debian-family machine, so there "
            "are no package copyright records to copy. What the platform "
            "supplies instead is named below, and the texts that are not "
            "already in `python/` or `tcl-tk/` are here at the top level."
        )
        index += [
            "",
            "- **Microsoft Visual C++ and Universal CRT runtime** (Windows) — "
            "redistributable under Microsoft's own terms, not an open-source "
            "licence, so there is no text to reproduce.",
            "- **OpenSSL and libffi**, which ship inside python.org's "
            "distributions — Apache-2.0 and MIT; `Apache-2.0.txt`.",
        ]
        written = ["Apache-2.0.txt"]
        for canonical, description in PLATFORM_TEXTS:
            source = os.path.join(repo, "licenses", canonical)
            if not os.path.exists(source):
                continue
            shutil.copyfile(source, os.path.join(staging, canonical))
            written.append(canonical)
            index.append(f"- **{description}** — `{canonical}`.")
        shutil.copyfile(
            os.path.join(repo, "licenses", "Apache-2.0.txt"),
            os.path.join(staging, "Apache-2.0.txt"),
        )
    index += [
        "",
        "## Relinking",
        "",
        "Any LGPL library collected from a Linux build machine — read",
        "`system/` to see whether this build has one — is unmodified and is",
        "linked dynamically. This is a folder build, so every such library is",
        "an ordinary file sitting in it and a recipient can replace one with a",
        "modified build of the same library by overwriting it. `system/` holds",
        "their terms; the AGPL text in `Tyche-LICENSE.txt` and the sources in",
        "the repository cover Tyche's own code.",
        "",
    ]

    with open(os.path.join(staging, "README.md"), "w", encoding="utf-8") as out:
        out.write("\n".join(index))
    return staging


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(format="%(levelname)s: %(message)s")
    argv = list(sys.argv[1:] if argv is None else argv)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    staging = argv[0] if argv else os.path.join(repo, "build", "licenses")
    collect(repo, staging)
    for directory, _subdirs, files in os.walk(staging):
        for name in sorted(files):
            path = os.path.join(directory, name)
            print(f"{os.path.getsize(path):>8}  {os.path.relpath(path, staging)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
