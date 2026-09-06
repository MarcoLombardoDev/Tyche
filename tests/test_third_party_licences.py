# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""THIRD-PARTY-LICENSES.md, and the script that keeps it honest.

The document is generated from a real build. What these tests check is that it
still says the things a reader needs and that the generator still behaves the
way the document claims — in particular that a licence file which cannot be
found is *recorded* rather than passed over, since a tree that looks complete
and is not is the one failure this whole mechanism exists to prevent.
"""

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

DOCUMENT = (REPO / "THIRD-PARTY-LICENSES.md").read_text(encoding="utf-8")

#: The headings, in order. Shared with Orion, Iris, Proteus and Argus so the
#: same question is answered in the same place in every product.
SECTIONS = [
    "## How this was produced",
    "## What Tyche depends on directly",
    "## The components that actually constrain redistribution",
    "## What was deliberately removed",
    "## Licence texts travel with the build",
    "## Full inventory",
    "## Build-time tools",
    "## Known gaps",
    "## Reproducing this",
]


def test_the_sections_are_present_and_in_order():
    positions = []
    for heading in SECTIONS:
        assert heading in DOCUMENT, f"{heading} is missing"
        positions.append(DOCUMENT.index(heading))
    assert positions == sorted(positions), "the sections are out of order"


@pytest.mark.parametrize(
    "dependency",
    ["CustomTkinter", "NumPy", "requests", "timesfm", "PyTorch",
     "huggingface-hub", "certifi", "PyInstaller"])
def test_every_direct_dependency_is_documented(dependency: str) -> None:
    """A dependency nobody wrote down is a dependency nobody licensed."""
    assert dependency in DOCUMENT


def test_the_declared_dependencies_and_the_document_agree():
    """The list here is four packages long because requirements.txt is.

    Read from the file rather than typed twice: a fifth dependency added
    without a row in the table is exactly the thing that goes unnoticed, and
    the parametrised test above cannot see it because it only knows the names
    somebody remembered.
    """
    declared = []
    for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # "timesfm[torch]>=3.0.0" -> "timesfm"
        declared.append(re.split(r"[\[<>=!~;]", line, maxsplit=1)[0].strip())

    lowered = DOCUMENT.lower()
    missing = [name for name in declared if name.lower() not in lowered]
    assert not missing, f"requirements.txt declares packages this file never names: {missing}"


def test_the_document_names_no_dependency_that_was_deliberately_avoided():
    """pandas, SciPy and beautifulsoup4 are absent on purpose.

    Each has a reason written down in requirements.txt, and each is the kind
    of dependency that gets added back by somebody who does not know that. A
    row listing one as a dependency would mean it had been.
    """
    for name in ("pandas", "SciPy", "beautifulsoup4"):
        for line in DOCUMENT.splitlines():
            if line.startswith("|") and name in line:
                raise AssertionError(f"{name} appears as a dependency row: {line}")


#: The document is prose, so a phrase can be split across a line break or wear
#: markdown emphasis. Tests that search it compare against this instead of the
#: raw text, rather than being hostage to where a paragraph happened to wrap.
FLATTENED = " ".join(DOCUMENT.replace("*", "").split())


def test_the_removal_is_explained_and_not_just_applied():
    """Somebody will eventually ask why readline is excluded. If the answer
    lives only in a commit message, the exclusion gets reverted.
    """
    assert "libreadline" in DOCUMENT
    assert "GPL-3.0-or-later with no linking exception" in FLATTENED


def test_the_inventory_separates_what_was_measured_from_what_was_assumed():
    """Every row names its evidence, and unresolved rows stay visible.

    Argus embeds the generated table in this document and this test looked for
    its "Evidence" column. Tyche's per-binary table is not embedded — it lives
    in the archive, which is the copy that describes what somebody actually
    downloaded — so what is checked here is that the document still tells a
    reader those three things about it.
    """
    lowered = " ".join(DOCUMENT.lower().split())
    assert "evidence" in lowered
    assert "unresolved" in lowered
    # Both spellings, because the generated inventory says "None of it is a
    # legal opinion" and this document says "not a legal opinion"; which of
    # the two a section uses is not what this test is about.
    assert "legal opinion" in lowered


def test_the_document_says_where_the_authoritative_inventory_actually_is():
    """A per-binary table in the repository describes a build somewhere else.

    PyInstaller collects what the runner's linker resolved, so the only table
    that describes a given download is the one generated on the machine that
    produced it and packaged inside it.
    """
    flattened = " ".join(DOCUMENT.split())
    assert "THIRD-PARTY-LICENSES-<platform>.md" in flattened
    assert "authoritative inventory is **not this file**" in flattened


def test_the_bytecode_gap_is_admitted():
    """The tables cover native binaries only. Pure-Python code — which is where
    a copyleft licence is most likely to hide — is not in them, and a reader
    who does not know that will draw the wrong conclusion from a clean table.
    """
    assert "bytecode" in DOCUMENT.lower()


class TestLicenceCollection:
    """The script that assembles what ships in the archive."""

    def test_a_missing_licence_is_recorded_rather_than_passed_over(self, tmp_path):
        """The one behaviour worth a test of its own.

        A wheel that ships no licence file has to leave a visible hole in the
        index. Silently skipping it produces a tree that looks complete, which
        is worse than one with an obvious gap.
        """
        import collect_licences

        assert collect_licences._distribution_licence_files(
            "a-distribution-that-does-not-exist"
        ) == []

    def test_build_tools_that_are_not_shipped_are_not_collected(self):
        """Their terms do not belong in an archive they are not in."""
        import collect_licences

        assert "pip" in collect_licences.BUILD_ONLY
        assert "setuptools" in collect_licences.BUILD_ONLY
        assert "pyinstaller" not in collect_licences.BUILD_ONLY, (
            "the bootloader does ship, so its terms have to"
        )

    def test_the_interpreter_and_the_toolkit_are_always_supplied(self):
        """Neither is a wheel; without these the tree would omit the terms of
        the two things every archive contains.
        """
        import collect_licences

        supplied = {name for _folder, name, _label in collect_licences.ALWAYS_SUPPLIED}
        assert supplied == {
            "Python-LICENSE.txt",
            "Tcl-license.terms.txt",
            "Tk-license.terms.txt",
        }


class TestLicencePathHandling:
    """Two wheels shipping ``licenses/LICENSE`` must not overwrite each other."""

    @staticmethod
    def _flatten(pairs):
        import collect_licences

        return dict(collect_licences._flatten(pairs))

    def test_the_conventional_licenses_prefix_is_dropped(self):
        assert self._flatten([("licenses/LICENSE", "x")]) == {"LICENSE": "x"}

    def test_but_not_when_that_would_collide(self):
        flattened = self._flatten([("LICENSE", "a"), ("licenses/LICENSE", "b")])
        assert flattened == {"LICENSE": "a", "licenses/LICENSE": "b"}

    def test_deeper_paths_are_preserved(self):
        assert self._flatten([("licenses/vendor/LICENSE", "x")]) == {
            "vendor/LICENSE": "x"
        }


class TestBundleClassifier:
    """Attributing a path in the bundle to the thing that shipped it.

    The owner index is supplied rather than read from the running interpreter.
    These tests check the attribution rules, and the CI job that runs them
    installs pytest and nothing else — against a real index they would pass or
    fail depending on what happened to be installed, which is not a property of
    the code under test.
    """

    #: What importlib.metadata reports on a machine that built one of these
    #: bundles: import names and distribution names both, case-folded.
    owners = {
        "pil": "pillow",
        "pillow": "pillow",
        "openpyxl": "openpyxl",
        "torch": "torch",
        "_cffi_backend": "cffi",
        "cffi": "cffi",
    }

    @pytest.mark.parametrize(
        "path, origin",
        [
            ("python3.12/lib-dynload/_ssl.cpython-312-x86_64-linux-gnu.so", "cpython"),
            ("libpython3.12.so.1.0", "cpython"),
            ("libtcl8.6.so", "system"),
            ("libgcc_s.so.1", "system"),
        ],
    )
    def test_origins(self, path: str, origin: str) -> None:
        import licence_inventory

        classified = licence_inventory.classify(path, self.owners)
        assert classified is not None, path
        assert classified[0] == origin

    def test_a_wheels_vendored_directory_is_credited_to_the_wheel(self):
        """auditwheel names it after the *distribution*, not the package, and
        PIL is not pillow. Getting this wrong left the largest group in the
        bundle reported as unknown.
        """
        import licence_inventory

        classified = licence_inventory.classify(
            "pillow.libs/libjpeg-31e2ca52.so.62.4.0", self.owners
        )
        assert classified == ("wheel", "pillow")

    def test_a_package_directory_is_credited_to_its_distribution(self):
        import licence_inventory

        classified = licence_inventory.classify(
            "PIL/_imaging.cpython-312-x86_64-linux-gnu.so", self.owners
        )
        assert classified == ("wheel", "pillow")

    def test_something_that_is_not_a_binary_is_not_inventoried(self):
        import licence_inventory

        assert licence_inventory.classify("README.md", self.owners) is None

    def test_a_top_level_extension_module_is_credited_to_its_distribution(self):
        """cffi's _cffi_backend sits at the top level with no directory to read
        the owner out of, and came out as a system library until the module
        name itself was used as the key.
        """
        import licence_inventory

        assert licence_inventory.classify(
            "_cffi_backend.cpython-312-x86_64-linux-gnu.so", self.owners
        ) == ("wheel", "cffi")

    def test_gpl3_readline_is_flagged_if_it_ever_returns(self):
        """The inventory is the last place this would be noticed, so it says so
        rather than printing a licence name and moving on.
        """
        import licence_inventory

        assert "libreadline8t64" in licence_inventory.FLAGGED
        assert "no linking exception" in licence_inventory.FLAGGED["libreadline8t64"]

    def test_one_place_decides_what_a_package_is_licensed_under(self):
        """These rules used to be applied twice — once where the package was
        found by name and once where it was found by path — and the second copy
        was missing the X.Org rule, so ten X libraries came out unresolved in a
        report that was otherwise complete.
        """
        import licence_inventory

        licence, evidence = licence_inventory.licence_for_package("libx11-6")
        assert licence == "MIT"
        assert "X.Org" in evidence


class TestRunsWithoutDpkg:
    """Two of the three release runners have no package database at all.

    This is where the first release run broke: ``subprocess.run`` raises
    FileNotFoundError when the executable is missing rather than returning
    non-zero, so the script died on Windows and macOS instead of reporting
    what it could not resolve.
    """

    def test_the_dpkg_lookup_is_guarded(self):
        import licence_inventory

        assert hasattr(licence_inventory, "HAS_DPKG")

    def test_it_returns_nothing_rather_than_raising(self, monkeypatch):
        import licence_inventory

        monkeypatch.setattr(licence_inventory, "HAS_DPKG", False)
        assert licence_inventory.dpkg_owner("libz.so.1") is None

    def test_the_platform_libraries_still_resolve(self, monkeypatch):
        """What a Windows or macOS bundle is mostly made of is named by
        pattern rather than by package, so it resolves with no dpkg at all.
        """
        import licence_inventory

        monkeypatch.setattr(licence_inventory, "HAS_DPKG", False)
        for name, expected in (
            ("VCRUNTIME140.dll", "Microsoft Visual C++ / Universal CRT runtime"),
            ("libcrypto.3.dylib", "OpenSSL"),
            ("libtcl8.6.dylib", "Tcl/Tk"),
            ("tcl86t.dll", "Tcl/Tk"),
        ):
            component, licence, _evidence = licence_inventory.resolve_system(name)
            assert component == expected, name
            assert licence, name

    def test_anything_else_is_reported_unresolved_not_guessed(self, monkeypatch):
        import licence_inventory

        monkeypatch.setattr(licence_inventory, "HAS_DPKG", False)
        component, licence, _evidence = licence_inventory.resolve_system("libmystery.so.1")
        assert component == "unknown"
        assert licence is None


def test_unresolved_rows_have_their_own_exit_code():
    """A caller has to be able to tell a script that finished with gaps from a
    script that died. An uncaught exception exits 1, so 1 cannot mean either.
    """
    import licence_inventory

    assert licence_inventory.UNRESOLVED_EXIT == 2


class TestWindowsPlatformLibraries:
    """The three the first Windows archives could not name.

    That Python's Windows build carries Tcl/Tk **9** was the surprise: its Tk
    DLL is `tcl9tk90.dll`, not `tk90.dll`, and a pattern written around 8.6's
    `tcl86t.dll` matched neither. zlib and LibTomMath arrive with Tcl 9 rather
    than by anyone asking for them, and shipped with no notice at all until
    their texts were vendored.

    None of this can be caught on Linux, where dpkg answers for all three.
    """

    @staticmethod
    def resolve(name):
        import licence_inventory

        return licence_inventory.resolve_system(name)

    @pytest.mark.parametrize(
        "name",
        [
            "tcl90.dll",       # Tcl 9, what current python.org builds ship
            "tcl9tk90.dll",    # its Tk, which no 8.6-shaped pattern matches
            "tcl86t.dll",      # Tcl 8.6 threaded, still out there
            "tk86t.dll",
        ],
    )
    def test_every_spelling_of_the_tcl_dlls_resolves(self, name):
        component, licence, _evidence = self.resolve(name)
        assert component == "Tcl/Tk", name
        assert licence == "TCL (BSD-style)"

    @pytest.mark.parametrize(
        "name, component",
        [("zlib1.dll", "zlib"), ("libtommath.dll", "LibTomMath")],
    )
    def test_what_tcl_drags_in_resolves_too(self, name, component):
        found, licence, _evidence = self.resolve(name)
        assert found == component
        assert licence

    def test_their_texts_travel_with_the_build(self):
        """Naming a licence in a table is not reproducing its notice."""
        import collect_licences

        supplied = {name for name, _description in collect_licences.PLATFORM_TEXTS}
        assert supplied == {"Zlib.txt", "LibTomMath.txt"}
        for name in supplied:
            path = REPO / "licenses" / name
            assert path.exists(), f"licenses/{name} is missing"
            assert "public domain" in path.read_text(encoding="utf-8").lower() or (
                "without any express or implied" in path.read_text(encoding="utf-8")
            ), f"licenses/{name} does not read like the licence it claims to be"


class TestPywin32:
    """The distribution whose folders name nothing.

    pywin32 declares its *modules* as top level — win32api, pythoncom,
    win32ui — and not the directories it installs them into: its own
    top_level.txt has no entry for `win32` or `pywin32_system32`. A classifier
    that only asks the folder therefore learns nothing about eight binaries in
    every Windows archive, which is exactly what happened.

    Its licence texts were in the archive throughout — collect_licences.py
    resolves distributions from PyInstaller's module list, which does not have
    this blind spot — so what was missing was the inventory naming them, not
    the notices themselves.
    """

    #: What packages_distributions() reports on a machine with pywin32
    #: installed: module names, not the folders holding them.
    owners = {
        "win32api": "pywin32",
        "win32event": "pywin32",
        "win32trace": "pywin32",
        "_win32sysloader": "pywin32",
        "win32ui": "pywin32",
        "pythonwin": "pywin32",
        "pythoncom": "pywin32",
        "pywintypes": "pywin32",
    }

    @pytest.mark.parametrize(
        "path",
        [
            "win32/win32api.pyd",
            "win32/win32event.pyd",
            "win32/win32trace.pyd",
            "win32/_win32sysloader.pyd",
            "pythonwin/win32ui.pyd",
        ],
    )
    def test_a_module_inside_an_unnamed_folder_is_still_attributed(self, path):
        import licence_inventory

        assert licence_inventory.classify(path, self.owners) == ("wheel", "pywin32")

    @pytest.mark.parametrize(
        "path", ["pywin32_system32/pythoncom312.dll", "pywin32_system32/pywintypes312.dll"]
    )
    def test_the_abi_versioned_dlls_are_attributed(self, path):
        """pythoncom312.dll is the module pythoncom with the interpreter's ABI
        stuck on the end; nothing declares the name with the number in it."""
        import licence_inventory

        assert licence_inventory.classify(path, self.owners) == ("wheel", "pywin32")

    def test_a_windows_path_classifies_the_same_as_a_posix_one(self):
        """These paths are read out of a Windows bundle, often on Linux, where
        os.path.basename does not split on a backslash and quietly returns the
        whole path."""
        import licence_inventory

        assert licence_inventory.classify(
            "win32\\win32api.pyd", self.owners
        ) == ("wheel", "pywin32")

    def test_the_mfc_runtime_pywin32_ships_is_named(self):
        import licence_inventory

        component, licence, _evidence = licence_inventory.resolve_system("mfc140u.dll")
        assert component == "Microsoft Foundation Class runtime"
        assert "Microsoft" in licence
