#!/usr/bin/env python
# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""Inventory the third-party code Tyche actually ships, and what licenses it.

THIRD-PARTY-LICENSES.md is generated from this script rather than written by
hand, because a hand-written list of a PyInstaller bundle is wrong the day
after it is written: PyInstaller collects whatever the build machine's linker
resolved, so the list changes when the runner image changes, not when anyone
edits the repository.

It attributes every native binary in a build to the thing that put it there:

  wheel   a Python wheel vendored it (Pillow's imaging libraries, and so on)
  cpython the interpreter and its standard library extension modules
  system  PyInstaller collected it from the build machine's own libraries

The first class is resolved from installed distribution metadata rather than
from a table kept here. A path like ``PIL/_imaging.cpython-312-x86_64.so``
names its own top-level package, and ``importlib.metadata`` knows which
distribution owns that package and what licence it declares. A table would
have to be edited every time a dependency gained a dependency, and would be
silently wrong in between.

Only the third class needs looking up, and on a Debian-family host dpkg knows
the answer: which package owns the file, and what that package's copyright
file says.

Two warnings about that lookup, both the reason this is a script rather than a
one-line shell pipeline.

The first: a debian/copyright file lists every licence appearing anywhere in
the *source* package, including test fixtures and build scripts. Reporting
that union is alarmist nonsense. What governs a shipped shared library is the
licence of that library's own sources, which in a machine-readable copyright
file is the stanza whose ``Files:`` pattern covers them.

The second: even the ``Files: *`` stanza is not that licence when the source
package builds several libraries under different terms. util-linux's default
stanza says GPL-2+, while the libraries these bundles take from it — libuuid
among them — carry BSD-3-clause in their own stanzas. Taking the default would
publish a wrong answer that looks authoritative.

So: the default stanza is a starting point, REVIEWED below is where a human
read the sub-stanza and recorded what it actually said, and anything the
script cannot resolve is reported as unresolved rather than guessed. A gap you
can see is worth more than a plausible-looking entry that is wrong.

Usage:

    python tools/licence_inventory.py --bundle linux=build/Tyche
    python tools/licence_inventory.py --bundle linux=dist/Tyche --markdown out.md

``--bundle`` takes any of three things, because at different points in a
release there is a different one to hand:

  a PyInstaller build directory   what the next archive will contain
  a single-file executable        what a published archive does contain
  an extracted bundle directory   the same, once somebody has unpacked it

Run it on a host of the same family as the release runner (Ubuntu, for the
Linux bundle) — otherwise the system-library lookup has nothing to consult and
every such library is reported unresolved.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

APP_NAME = "Tyche"

#: Exit code for "the report was written, and some rows in it need a human".
#: Deliberately not 1: an uncaught exception exits 1 too, and a caller that
#: cannot tell the two apart treats a script that *died* as a script that
#: merely found something unattributable. That is not a hypothetical — the
#: v1 release workflow did exactly that, and two archives shipped with no
#: inventory in them while the log said "warning".
UNRESOLVED_EXIT = 2

#: Wheel-vendored libraries carry an eight-hex-digit tag inserted by auditwheel
#: so two wheels can vendor different builds of the same library without
#: colliding.
VENDOR_TAG = re.compile(r"-[0-9a-f]{8}\.(?:so|dylib)")

#: Where each origin's licence terms are stated, for the report to cite.
ORIGIN_SOURCES = {
    "wheel": "the wheel's own distribution metadata",
    "cpython": "the Python Software Foundation License, version 2",
    "system": "the build machine's package copyright records",
}

#: Sub-library licences a human verified by reading the stanza named in
#: ``evidence``, because the copyright file's default stanza does not describe
#: the library actually shipped. Keyed by binary package name.
REVIEWED: dict[str, tuple[str, str]] = {
    "libblkid1": ("LGPL-2.1-or-later", "Files: libblkid/* — default stanza says GPL-2+"),
    "libmount1": ("LGPL-2.1-or-later", "Files: libmount/* — default stanza says GPL-2+"),
    "libuuid1": ("BSD-3-Clause", "Files: libuuid/* — default stanza says GPL-2+"),
    "libbsd0": (
        "BSD-3-Clause AND BSD-2-Clause AND ISC",
        "per-file stanzas, all permissive BSD/ISC variants",
    ),
    "libmd0": (
        "BSD-3-Clause AND BSD-2-Clause AND ISC",
        "per-file stanzas, all permissive BSD/ISC variants",
    ),
    "libjpeg-turbo8": (
        "IJG AND BSD-3-Clause AND Zlib",
        "per-file stanzas; no Files: * stanza exists",
    ),
}

#: Debian's copyright files use their own licence shorthand. Translating it to
#: SPDX makes the report comparable with the wheel metadata, which already
#: speaks SPDX — but only where the translation is unambiguous. Anything not
#: listed here is reported exactly as Debian wrote it rather than guessed at.
SPDX = {
    "Expat": "MIT",
    "MIT/X": "MIT",
    "MIT/X11": "MIT",
    "MIT/X Consortium License": "MIT",
    "GPL-2": "GPL-2.0-only",
    "GPL-2+": "GPL-2.0-or-later",
    "GPL-3+": "GPL-3.0-or-later",
    "LGPL-2+": "LGPL-2.0-or-later",
    "LGPL-2.1+": "LGPL-2.1-or-later",
    "BSD-2-clause": "BSD-2-Clause",
    "BSD-3-clause": "BSD-3-Clause",
    "BSD-3-clause or GPL-2": "BSD-3-Clause OR GPL-2.0-only",
    "BSD-variant": "bzip2-1.0.6",
    "PD": "public domain",
    "public-domain": "public domain",
    "libpng": "Libpng",
    "FTL": "FTL (FreeType License)",
    "LGPL-2.1+ or MPL-1.1 or GPL-2+": "LGPL-2.1-or-later OR MPL-1.1 OR GPL-2.0-or-later",
    "GPL-2+ or AFL-2.1, and Expat and Tcl-BSDish": "AFL-2.1 OR GPL-2.0-or-later",
    "BSD-3-clause-Cambridge with BINARY LIBRARY-LIKE PACKAGES exception": (
        "BSD-3-Clause (PCRE2 variant)"
    ),
}

#: Resolutions a reader should not take on trust. These resolve to *something*,
#: but the something is disputed or unrepresentative, and the report says so
#: instead of presenting a clean answer that might be wrong.
FLAGGED = {
    "libcom-err2": (
        "Ubuntu's copyright file has no stanza for lib/et, so the GPL-2 default "
        "applies by omission; upstream e2fsprogs licenses com_err under MIT. "
        "Confirm before relying on either reading."
    ),
    "libreadline8t64": (
        "GPL-3.0-or-later with no linking exception. Nothing here should be "
        "linking it: it arrives only with the standard library's optional "
        "readline extension, which the build excludes for exactly this reason. "
        "If it appears in this table, that exclusion has stopped working."
    ),
}

#: Packages whose copyright file is free-form prose rather than machine
#: readable, read once by a human and recorded here with the phrase that
#: identifies the licence.
FREEFORM: dict[str, tuple[str, str]] = {
    "libgcc-s1": (
        "GPL-3.0-or-later WITH GCC-exception-3.1",
        "'version 3.1 of the GCC Runtime Library Exception'",
    ),
    "libstdc++6": (
        "GPL-3.0-or-later WITH GCC-exception-3.1",
        "'version 3.1 of the GCC Runtime Library Exception'",
    ),
    "libgomp1": (
        "GPL-3.0-or-later WITH GCC-exception-3.1",
        "'version 3.1 of the GCC Runtime Library Exception'",
    ),
    # The GNU Objective-C runtime. Its copyright file names the runtime
    # libraries the exception covers, and libobjc is on that list — worth
    # checking rather than assuming, since without the exception this would be
    # a plain GPL-3 library sitting in the bundle.
    "libobjc4": (
        "GPL-3.0-or-later WITH GCC-exception-3.1",
        "'licensed under ... version 3.1 of the GCC Runtime Library "
        "Exception', whose list of covered libraries includes libobjc",
    ),
    "libfontconfig1": ("MIT", "'Permission to use, copy, modify' — Keith Packard, fontconfig"),
    # tkinter's toolkit. Debian's copyright file lists the copyright holders
    # first and states the terms further down; both packages carry the same
    # permissive Tcl licence, quoted here by its opening sentence.
    "libtcl8.6": (
        "TCL (BSD-style)",
        "'This software is copyrighted by the Regents of the University of "
        "California, Sun Microsystems, Inc., Scriptics Corporation'",
    ),
    "libtk8.6": (
        "TCL (BSD-style)",
        "'This software is copyrighted by the Regents of the University of "
        "California, Sun Microsystems, Inc.'",
    ),
    # BLT arrives with tk8.6 rather than by anyone asking for it. Its
    # copyright file has Files:/License: stanzas but no Format: header, so it
    # reads as free-form to a parser and had to be read rather than parsed.
    "tk8.6-blt2.5": (
        "MIT",
        "Files: * — License: MIT-1 (Lucent Technologies), in a copyright file "
        "with no Format: header",
    ),
    "libgcrypt20": ("LGPL-2.1-or-later", "'Lesser General Public License', version 2.1"),
    "libpixman-1-0": ("MIT", "'MIT license'"),
}

#: Binaries that come from the platform rather than from a package manager, so
#: dpkg has nothing to say about them. The Windows bundle is almost entirely
#: this: the Universal CRT forwarders and the Visual C++ runtime, which
#: Microsoft licenses for redistribution under its own terms and not under any
#: open-source licence, plus the OpenSSL and libffi builds that ship inside
#: python.org's own Windows and macOS distributions.
PLATFORM_COMPONENTS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"^(api-ms-win-|ucrtbase\.dll$|VCRUNTIME140|MSVCP140)", re.I),
        "Microsoft Visual C++ / Universal CRT runtime",
        "Microsoft redistributable terms — not an open-source licence",
    ),
    # The MFC runtime, which pywin32 ships for win32ui. Same legal basis as
    # the row above and a different file, so it needs saying separately.
    (
        re.compile(r"^mfc\d+u?\.dll$", re.I),
        "Microsoft Foundation Class runtime",
        "Microsoft redistributable terms — not an open-source licence",
    ),
    (re.compile(r"^lib(ssl|crypto)[-.]", re.I), "OpenSSL", "Apache-2.0"),
    (re.compile(r"^libffi[-.]", re.I), "libffi", "MIT"),
    (re.compile(r"^lib(tcl|tk)\d", re.I), "Tcl/Tk", "TCL (BSD-style)"),
    # Tcl/Tk names its Windows DLLs differently in every generation: 8.6 ships
    # tcl86t.dll and tk86t.dll — the trailing "t" is the threaded build — while
    # 9.0, which is what current python.org builds carry, ships tcl90.dll and
    # tcl9tk90.dll. Matching "starts with tcl or tk" rather than trying to
    # predict the numbering is the only version of this that keeps working:
    # two patterns written for 8.6 already missed 9.0 once.
    (re.compile(r"^(tcl|tk)[0-9a-z]*\.dll$", re.I), "Tcl/Tk", "TCL (BSD-style)"),
    # Both arrive with Tcl 9 rather than by anyone asking for them, and both
    # ship in the Windows archive with no package manager to name them.
    # Their texts are vendored in licenses/ and travel with the build.
    (re.compile(r"^zlib1\.dll$", re.I), "zlib", "Zlib"),
    (re.compile(r"^libtommath\.dll$", re.I), "LibTomMath",
     "public domain (the LibTom licence: 'released into the public domain')"),
    # Ships inside python.org's Windows build for the standard library's
    # sqlite3 module. Public domain, so unlike the others there is no notice
    # to reproduce and no text to vendor — but "public domain" is an answer
    # and "unresolved" is not, and the difference is what this table is for.
    (re.compile(r"^sqlite3\.dll$", re.I), "SQLite",
     "public domain (sqlite.org/copyright.html: 'SQLite Is Public Domain')"),
]

#: The X.Org and XCB stacks: dozens of packages, one licence between them, all
#: with free-form copyright files. Listing each by hand would be noise.
XORG_MIT = "MIT"
XORG_EVIDENCE = "X.Org / XCB standard copyright — MIT/X11 permission notice"


@dataclass
class Entry:
    """One native binary in the bundle and what is known about its licence."""

    path: str
    origin: str
    component: str
    licence: str | None = None
    evidence: str | None = None
    flag: str | None = None

    @property
    def resolved(self) -> bool:
        return self.licence is not None


@dataclass
class Inventory:
    platform: str
    root: str
    entries: list[Entry] = field(default_factory=list)

    @property
    def unresolved(self) -> list[Entry]:
        return [e for e in self.entries if not e.resolved]


#: A macOS framework's actual Mach-O binary has no extension at all: it is
#: Foo.framework/Versions/A/Foo. Matching only on extensions silently skips
#: every framework in the bundle.
FRAMEWORK_BINARY = re.compile(r"(?:^|/)(?P<name>[^/]+)\.framework/Versions/[^/]+/(?P=name)$")


def is_native(rel: str) -> bool:
    """True for anything the loader maps as machine code at run time."""
    name = os.path.basename(rel)
    return (
        ".so" in name
        or name.endswith((".dylib", ".dll", ".pyd"))
        or FRAMEWORK_BINARY.search(rel.replace("\\", "/")) is not None
    )


def _owners() -> dict[str, str]:
    """Lowercased lookup key -> the distribution that owns it.

    Two kinds of key go in, because a bundle path can name either. Most native
    binaries sit inside their package's directory — ``PIL/_imaging...so`` — so
    the top-level *import* name is what the path gives. But auditwheel and
    delocate put a wheel's vendored libraries in a sibling directory named
    after the *distribution* instead — ``pillow.libs/libjpeg-31e2ca52.so`` —
    and PIL is not pillow. Indexing both, case-folded, is what stops the
    largest group in the bundle being reported as unknown.
    """
    from importlib.metadata import distributions, packages_distributions

    index: dict[str, str] = {}
    for package, owning in packages_distributions().items():
        for name in owning:
            index.setdefault(package.lower(), name)
    for dist in distributions():
        name = dist.metadata["Name"]
        if name:
            index.setdefault(name.lower(), name)
            index.setdefault(name.lower().replace("-", "_"), name)
    return index


def _declared_licence(distribution_name: str) -> str | None:
    """What a distribution's own metadata says, in one line.

    ``License-Expression`` is SPDX by definition and is used as-is. The older
    free-form ``License`` field is frequently a whole licence text pasted into
    a header; only its first line is reported, and a field that is really a
    licence text rather than a name is reported as the classifier says instead.
    """
    from importlib.metadata import distribution

    try:
        metadata = distribution(distribution_name).metadata
    except Exception:
        return None
    expression = metadata.get("License-Expression")
    if expression:
        return expression.strip()
    classifiers = [
        value.split("::")[-1].strip()
        for value in metadata.get_all("Classifier") or ()
        if value.startswith("License ::")
    ]
    declared = (metadata.get("License") or "").strip()
    first = declared.splitlines()[0].strip() if declared else ""
    if first and len(first) <= 60:
        return first
    if classifiers:
        return " / ".join(dict.fromkeys(classifiers))
    return first[:60] or None


def classify(rel: str, owners: dict[str, str]) -> tuple[str, str] | None:
    """Attribute one bundle-relative path to the component that shipped it.

    Returns ``(origin, component)``, or None when the path is not a native
    binary. CPython is tested before the package lookup: a stdlib extension
    module sits in a path that no distribution owns, and calling it unknown
    would leave the largest single group in the bundle unattributed.
    """
    if not is_native(rel):
        return None
    # Normalise first, then take the file name from the normalised path.
    # os.path.basename does not split on a backslash when it runs on Linux,
    # and these paths come out of a Windows bundle read on a Linux machine, so
    # deriving the name from the raw string returns the whole path.
    normalised = rel.replace("\\", "/")
    base = normalised.split("/")[-1]
    lower = normalised.lower()

    if (
        base.startswith(("libpython3", "python3"))
        or lower.startswith(("python3", "lib-dynload/"))
        or "/lib-dynload/" in lower
        or lower.startswith("python.framework/")
        # A .pyd sitting at the top level is a stdlib extension module; the
        # ones belonging to a package sit inside that package's directory.
        or (base.endswith(".pyd") and "/" not in lower)
    ):
        return "cpython", "CPython"

    # A top-level extension module belongs to whatever distribution installed
    # it — cffi's _cffi_backend, or the mypyc-compiled module a package builds
    # under a hashed name. There is no directory to read the owner out of, so
    # the module name itself is the key.
    if "/" not in lower and (".so" in base or base.endswith((".pyd", ".dylib"))):
        owner = owners.get(base.split(".")[0].lower())
        if owner:
            return "wheel", owner

    if "/" in lower or VENDOR_TAG.search(base):
        # auditwheel and delocate put a wheel's vendored libraries in a sibling
        # directory named after the distribution with .libs or .dylibs
        # appended; everything else sits inside its own package directory.
        head = re.sub(r"\.(libs|dylibs)$", "", lower.split("/")[0])
        for candidate in (head, head.replace("-", "_"), head.replace("_", "-")):
            owner = owners.get(candidate)
            if owner:
                return "wheel", owner

        # A directory that names no distribution is not the end of it. pywin32
        # declares its *modules* as top level — win32api, pythoncom, win32ui —
        # and not the directories it installs them into: its top_level.txt has
        # no entry for `win32` or `pywin32_system32` at all. So the folder
        # answers nothing and the file name answers everything, and eight
        # binaries in every Windows archive came out unknown because only the
        # folder was ever asked.
        #
        # The second candidate drops a trailing version number, which is how
        # pywin32 names the two DLLs that carry the interpreter's ABI:
        # pythoncom312.dll is the module pythoncom.
        stem = base.split(".")[0].lower()
        for candidate in (stem, re.sub(r"\d+$", "", stem)):
            owner = owners.get(candidate)
            if owner:
                return "wheel", owner
    return "system", ""


#: Whether the build machine can be asked which package owns a library. Only a
#: Debian-family one can. Checked once, and checked at all because
#: ``subprocess.run`` *raises* on a missing executable rather than returning
#: non-zero: without this the script died outright on the Windows and macOS
#: runners, and the release published two archives with no inventory in them.
HAS_DPKG = shutil.which("dpkg-query") is not None


def dpkg_owner(basename: str) -> str | None:
    """Ask dpkg which package owns a library, trying shorter sonames first.

    ``None`` everywhere dpkg does not exist, which is every Windows and macOS
    build. The caller falls back to PLATFORM_COMPONENTS, and whatever that
    does not name is reported unresolved — which is the honest answer for a
    machine with no package database to consult.
    """
    if not HAS_DPKG:
        return None
    candidates = [basename]
    trimmed = re.match(r"^(.*\.so\.\d+)\.", basename)
    if trimmed:
        candidates.append(trimmed.group(1))
    for candidate in candidates:
        for prefix in ("/usr/lib/x86_64-linux-gnu/", "/lib/x86_64-linux-gnu/", "/usr/lib/"):
            found = subprocess.run(
                ["dpkg-query", "-S", prefix + candidate],
                capture_output=True,
                text=True,
            )
            if found.returncode == 0 and found.stdout.strip():
                return found.stdout.split(":")[0].strip()
    return None


def default_stanza_licence(package: str) -> tuple[str | None, bool]:
    """The ``Files: *`` licence from a package's copyright file.

    Returns ``(licence, machine_readable)``. A free-form copyright file yields
    ``(None, False)`` — it needs a human, which is what FREEFORM records.
    """
    path = f"/usr/share/doc/{package.split(':')[0]}/copyright"
    if not os.path.exists(path):
        return None, False
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    if "Format:" not in text.split("\n\n")[0]:
        return None, False
    for stanza in text.split("\n\n"):
        files = licence = None
        for line in stanza.splitlines():
            if line.startswith("Files:"):
                files = line[len("Files:"):].strip()
            elif line.startswith("License:") and files is not None:
                licence = line[len("License:"):].strip()
                break
        if files == "*" and licence:
            return licence, True
    return None, True


def licence_for_package(package: str) -> tuple[str | None, str]:
    """``(licence, evidence)`` for one Debian binary package.

    The single place these rules live. They used to be applied twice — once
    where the package was found by name and once where it was found by path —
    and the second copy was missing the X.Org rule, so ten X libraries came
    out unresolved in a report that was otherwise complete.
    """
    if package in REVIEWED:
        licence, evidence = REVIEWED[package]
        return licence, f"reviewed: {evidence}"
    if package in FREEFORM:
        licence, evidence = FREEFORM[package]
        return licence, f"free-form copyright: {evidence}"
    if package.startswith(("libx", "libxcb", "libxkbcommon")):
        return XORG_MIT, f"free-form copyright: {XORG_EVIDENCE}"
    licence, machine_readable = default_stanza_licence(package)
    if licence:
        return SPDX.get(licence, licence), "debian/copyright, Files: * stanza"
    if not machine_readable:
        return None, "free-form copyright — needs review"
    return None, "no Files: * stanza — needs review"


def resolve_system(basename: str) -> tuple[str, str | None, str | None]:
    """Resolve one system library to ``(package, licence, evidence)``."""
    package = dpkg_owner(basename)
    if package is None:
        for pattern, component, licence in PLATFORM_COMPONENTS:
            if pattern.match(basename):
                return component, licence, "shipped by the platform, not by a package manager"
        return "unknown", None, None
    licence, evidence = licence_for_package(package)
    return package, licence, evidence


def _paths_from_build_directory(root: str) -> list[tuple[str, str]] | None:
    """``(bundle path, source path)`` from PyInstaller's own record of a build.

    This is the most accurate of the three inputs, because it carries where
    each file came *from* — so a system library is resolved by its real path
    rather than by matching its name against the ones dpkg happens to know.
    """
    toc = os.path.join(root, "Analysis-00.toc")
    if not os.path.exists(toc):
        return None
    with open(toc, encoding="utf-8") as handle:
        parsed = ast.literal_eval(handle.read())
    found = []
    for section in parsed:
        if not isinstance(section, list):
            continue
        for entry in section:
            if (isinstance(entry, tuple) and len(entry) == 3
                    and entry[2] in ("BINARY", "EXTENSION")):
                found.append((str(entry[0]), str(entry[1])))
    return found


def _paths_from_executable(path: str) -> list[tuple[str, str]]:
    """``(bundle path, '')`` for the binaries inside a single-file executable.

    A ``--onefile`` build is an archive with a bootloader in front of it, so
    there is nothing to walk: the contents have to be read out of it. Needs
    PyInstaller importable, which any machine that produced the file has.
    """
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(path)
    return [(name, "") for name, record in reader.toc.items() if record[-1] == "b"]


def _paths_from_tree(root: str) -> list[tuple[str, str]]:
    """``(bundle path, source path)`` for an extracted bundle directory."""
    found = []
    for directory, _subdirs, files in os.walk(root):
        for name in sorted(files):
            full = os.path.join(directory, name)
            found.append((os.path.relpath(full, root), full))
    return found


def bundle_contents(path: str) -> list[tuple[str, str]]:
    """Whatever ``--bundle`` was pointed at, as a list of bundle paths."""
    if os.path.isfile(path):
        return _paths_from_executable(path)
    from_build = _paths_from_build_directory(path)
    return from_build if from_build is not None else _paths_from_tree(path)


def take_inventory(platform: str, root: str) -> Inventory:
    inventory = Inventory(platform=platform, root=root)
    owners = _owners()
    for rel, source in bundle_contents(root):
        # PyInstaller lays a bundle out differently per platform: _internal/ on
        # Windows and Linux, Contents/Frameworks and Contents/Resources inside
        # an .app on macOS. Attribution rules are written against the path
        # *below* that prefix, so strip it.
        inner = rel.replace("\\", "/").split("_internal/", 1)[-1]
        for prefix in ("Contents/Frameworks/", "Contents/Resources/", "Contents/MacOS/"):
            inner = inner.split(prefix, 1)[-1]
        classified = classify(inner, owners)
        if classified is None:
            continue
        origin, component = classified
        if origin == "system":
            # Prefer the real source path when there is one: dpkg answers
            # exactly rather than by matching a name it may not recognise.
            if (HAS_DPKG and source and "site-packages" not in source
                    and os.path.exists(source)):
                found = subprocess.run(
                    ["dpkg-query", "-S", os.path.realpath(source)],
                    capture_output=True,
                    text=True,
                )
                package = (found.stdout.split(":")[0].strip()
                           if found.returncode == 0 and found.stdout.strip() else None)
            else:
                package = None
            if package is None:
                package, licence, evidence = resolve_system(os.path.basename(inner))
            else:
                licence, evidence = licence_for_package(package)
            inventory.entries.append(
                Entry(inner, origin, package, licence, evidence, FLAGGED.get(package))
            )
        elif origin == "cpython":
            inventory.entries.append(
                Entry(inner, origin, component, "PSF-2.0", ORIGIN_SOURCES[origin])
            )
        else:
            inventory.entries.append(
                Entry(inner, origin, component, _declared_licence(component),
                      ORIGIN_SOURCES[origin])
            )
    inventory.entries.sort(key=lambda e: (e.origin, e.component.lower(), e.path))
    return inventory


def grouped(inventory: Inventory) -> dict[tuple[str, str], list[Entry]]:
    groups: dict[tuple[str, str], list[Entry]] = {}
    for entry in inventory.entries:
        groups.setdefault((entry.origin, entry.component), []).append(entry)
    return dict(sorted(groups.items(), key=lambda item: (item[0][0], item[0][1].lower())))


def summarise(inventory: Inventory) -> None:
    by_origin: dict[str, int] = {}
    for entry in inventory.entries:
        by_origin[entry.origin] = by_origin.get(entry.origin, 0) + 1

    print(f"# {inventory.platform}: {len(inventory.entries)} native binaries")
    for origin, count in sorted(by_origin.items()):
        print(f"  {origin:8} {count}")
    print()
    for (origin, component), entries in grouped(inventory).items():
        licences = sorted({e.licence or "UNRESOLVED" for e in entries})
        print(f"{origin:8} {component:28} {len(entries):3}  {', '.join(licences)}")
    flagged = sorted({(e.component, e.flag) for e in inventory.entries if e.flag})
    if flagged:
        print("\nflagged:")
        for component, note in flagged:
            print(f"  {component}: {note}")
    if inventory.unresolved:
        print(f"\nunresolved: {len(inventory.unresolved)}")
        for entry in inventory.unresolved:
            print(f"  {entry.path}  ({entry.component})  {entry.evidence}")


def missing_notices(inventory: Inventory, licences: str) -> list[str]:
    """Distributions that put a binary in the bundle and no licence text in it.

    Only the ones the *owner lookup* named. What that lookup returns is a real
    distribution name, which is exactly what collect_licences.py writes its
    directories under, so the two sides of the comparison are the same kind of
    thing. Curated labels — a heading a human wrote for a family of libraries —
    would report a gap on every build and are left out.

    The failure it is here to catch: a dependency starts shipping a native
    extension, the inventory attributes it happily, and its notice travels
    nowhere. The inventory alone cannot see that; it only reports the rows it
    could not attribute, and this one it could.
    """
    root = os.path.join(licences, "python")
    if not os.path.isdir(root):
        return []
    shipped = {name.lower() for name in os.listdir(root)}
    known = {name.lower() for name in _owners().values()}
    named = {
        entry.component
        for entry in inventory.entries
        if entry.origin == "wheel" and entry.component.lower() in known
    }
    return sorted(name for name in named if name.lower() not in shipped)


def as_markdown(inventories: list[Inventory]) -> str:
    """The table that goes into the archive, one section per platform."""
    lines = [
        f"# What this {APP_NAME} build contains",
        "",
        "Generated by `tools/licence_inventory.py` from the build itself, not",
        "written by hand. Every row names the evidence it rests on so it can be",
        "re-checked. None of it is a legal opinion.",
        "",
    ]
    for inventory in inventories:
        lines += [
            f"## {inventory.platform} — {len(inventory.entries)} native binaries",
            "",
            "| Component | Files | Licence | Evidence |",
            "|---|---|---|---|",
        ]
        for (origin, component), entries in grouped(inventory).items():
            licences = sorted({e.licence or "**unresolved**" for e in entries})
            evidence = sorted({e.evidence or "" for e in entries})
            lines.append(
                f"| `{component or 'unknown'}` ({origin}) | {len(entries)} | "
                f"{', '.join(licences)} | {'; '.join(evidence)} |"
            )
        lines.append("")
        flagged = sorted({(e.component, e.flag) for e in inventory.entries if e.flag})
        if flagged:
            lines += ["**Flagged for review**", ""]
            lines += [f"- `{component}` — {note}" for component, note in flagged]
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--bundle",
        action="append",
        required=True,
        metavar="PLATFORM=PATH",
        help=f"a build directory, executable or extracted bundle, "
             f"e.g. linux=build/{APP_NAME}",
    )
    parser.add_argument("--json", help="write the full inventory here")
    parser.add_argument("--markdown", help="write the per-platform table here")
    parser.add_argument(
        "--licences",
        help="the licence tree going into the bundle, checked for a notice "
             "per distribution",
    )
    args = parser.parse_args(argv)

    inventories = []
    for spec in args.bundle:
        if "=" not in spec:
            parser.error(f"--bundle wants PLATFORM=PATH, got {spec!r}")
        platform, path = spec.split("=", 1)
        if not os.path.exists(path):
            parser.error(f"no such path: {path}")
        inventory = take_inventory(platform, path)
        summarise(inventory)
        print()
        inventories.append(inventory)

    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as handle:
            handle.write(as_markdown(inventories))
        print(f"wrote {args.markdown}")

    if args.json:
        payload = {inv.platform: [vars(e) for e in inv.entries] for inv in inventories}
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, sort_keys=True)
        print(f"wrote {args.json}")

    gaps = []
    if args.licences:
        for inv in inventories:
            for name in missing_notices(inv, args.licences):
                gaps.append(f"{inv.platform}: {name} ships a binary and no licence text")
        for gap in gaps:
            print(f"no notice: {gap}")

    if any(inv.unresolved for inv in inventories) or gaps:
        return UNRESOLVED_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(main())
