# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""What must and must not end up inside a built bundle.

There is one thing in here, and it is not about size.

PyInstaller collects the standard library's optional ``readline`` extension by
default. It links ``libreadline``, which is **GPL-3.0-or-later with no linking
exception** — a licence Tyche does not otherwise carry, pulled into every Linux
archive it publishes, for a module nothing in the program uses. AGPL-3.0 and
GPL-3.0 combine without trouble, so this is not a licence conflict; it is a
component in the archive's inventory that nobody chose and nobody needs, and it
arrived by default rather than by decision.

``libpython`` does not link it; only that module does. Nothing in Tyche
reads a line from an interactive prompt. So it is excluded — and pinned here,
because an exclusion nobody checks is an exclusion that comes back the next
time somebody regenerates a spec file.
"""

import pathlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

#: Every file that decides what goes into a bundle. More than one, in two of
#: these projects, because build.py generates its own spec rather than using
#: the versioned one — so they are separate inputs to the same decision, and
#: nothing but this test notices when they disagree.
BUILD_INPUTS = ['Tyche.spec']


@pytest.fixture(scope="module", params=BUILD_INPUTS)
def build_input(request) -> str:
    path = REPO / request.param
    if not path.exists():
        pytest.fail(f"{request.param} is gone; this test guards a file that no "
                    "longer decides anything")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "module, reason",
    [
        ("readline", "links libreadline, GPL-3.0-or-later with no linking exception"),
        ("rlcompleter", "imports readline and exists for nothing else"),
    ],
)
def test_the_gpl3_readline_chain_is_excluded(build_input: str, module: str,
                                             reason: str) -> None:
    assert f'"{module}"' in build_input or f"'{module}'" in build_input, (
        f"{module} is not excluded from the bundle — {reason}"
    )


def test_the_exclusion_says_why():
    """A bare name in an exclusion list is deleted by the next person who
    tidies it, because nothing tells them what it is for.
    """
    for name in BUILD_INPUTS:
        text = (REPO / name).read_text(encoding="utf-8")
        assert "GPL-3" in text, f"{name} excludes readline without saying why"


def test_the_licence_tooling_is_present():
    """The archive's licence tree and its inventory are both generated at build
    time; the release workflow calls these two by path.
    """
    for tool in ("tools/collect_licences.py", "tools/licence_inventory.py"):
        assert (REPO / tool).exists(), f"{tool} is missing"


def test_the_canonical_texts_the_wheels_do_not_ship_are_vendored():
    """CPython and Tcl/Tk are not wheels, so nothing carries their terms.

    Without these the licence tree would be missing the terms of the
    interpreter that runs the application and the toolkit it draws with —
    which is to say, of the two things every single archive contains.
    """
    for name in ("Python-LICENSE.txt", "Tcl-license.terms.txt",
                 "Tk-license.terms.txt", "Apache-2.0.txt"):
        path = REPO / "licenses" / name
        assert path.exists(), f"licenses/{name} is missing"
        assert len(path.read_text(encoding="utf-8")) > 1000, (
            f"licenses/{name} is too short to be a licence"
        )


class TestLineEndings:
    """`.gitattributes` decides these, and both directions can break a launcher.

    `start.cmd` is read by cmd.exe, which has historically needed CRLF for
    `goto` in particular. `start.sh` is read by /bin/sh, which treats a
    trailing CR as part of the last word on the line — so a checkout with
    autocrlf on produces a script that dies with "bad interpreter". Neither is
    something a contributor's local git config should be able to decide.
    """

    def test_the_rules_are_pinned_in_the_repository(self):
        rules = (REPO / ".gitattributes").read_text(encoding="utf-8")
        assert "*.cmd text eol=crlf" in rules
        assert "*.sh text eol=lf" in rules

    def test_the_posix_launcher_has_no_carriage_returns(self):
        assert b"\r" not in (REPO / "packaging" / "start.sh").read_bytes()

    def test_the_posix_launcher_starts_with_a_shebang(self):
        first = (REPO / "packaging" / "start.sh").read_bytes().split(b"\n", 1)[0]
        assert first == b"#!/bin/sh", first


class TestGovernanceTemplates:
    """Tyche has no CLA, and nothing may ask a contributor for one.

    A CLA exists to let an owner relicense a contribution commercially. With
    no commercial tier there is nothing to relicense into, so asking would be
    collecting a right nobody intends to use. Argus's templates — which these
    were copied from — do ask, which is exactly how such a line survives a
    copy.
    """

    def test_the_templates_are_present(self):
        for name in (".github/PULL_REQUEST_TEMPLATE.md",
                     ".github/ISSUE_TEMPLATE/config.yml"):
            assert (REPO / name).exists(), f"{name} is missing"

    def test_nothing_asks_a_contributor_to_agree_to_a_cla(self):
        for name in (".github/PULL_REQUEST_TEMPLATE.md",
                     ".github/ISSUE_TEMPLATE/config.yml"):
            text = (REPO / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if "CLA" not in stripped:
                    continue
                # Saying there is no CLA is the one place the acronym belongs,
                # and it is said in Italian in the issue chooser and English in
                # the comment on the pull-request checklist.
                denial = any(
                    word in stripped.lower()
                    for word in ("nessun cla", "no cla", "senza cla")
                )
                assert denial, f"{name} mentions a CLA that does not exist: {line}"

    def test_the_checklist_names_the_command_that_actually_runs_the_suite(self):
        """`python -m pytest tests/ -q` alone skips the whole interface."""
        checklist = (REPO / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(
            encoding="utf-8")
        assert "TYCHE_REQUIRE_GUI=1" in checklist
        assert "ruff check ." in checklist


class TestApplicationIcon:
    """One letter, black, on white, in a serif face — the same drawing in all
    four products, differing only in the letter.

    Committed rather than generated during the build: a release that depended
    on which fonts a runner happened to have would produce a different icon
    depending on the machine, or none.
    """

    ICO = REPO / "assets/app_icon.ico"
    PNG = REPO / "assets/app_icon.png"

    def test_both_files_are_in_the_repository(self):
        assert self.ICO.is_file(), f"{self.ICO} is missing"
        assert self.PNG.is_file(), f"{self.PNG} is missing"

    def test_the_ico_carries_every_size_windows_asks_for(self):
        """An .ico with only one frame makes Windows scale it, and a 256-pixel
        letter scaled to 16 is a grey smudge on the taskbar.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.ICO) as icon:
            sizes = {size[0] for size in icon.info["sizes"]}
        assert {16, 24, 32, 48, 64, 128, 256} <= sizes, f"only {sorted(sizes)}"

    def test_the_png_is_big_enough_for_a_retina_dock(self):
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.PNG) as png:
            assert png.size == (512, 512)

    def test_the_frame_is_there_at_every_size(self):
        """The four products draw their window icon from different sources —
        Qt scales the 512-pixel PNG, Tk picks the matching frame out of the
        .ico — so a rule that dropped the frame at small sizes made one
        product look like two and the four look like four families. Reported
        exactly that way: one had a black border and another did not.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.ICO) as icon:
            sizes = sorted(icon.info["sizes"])
            for size in sizes:
                icon.size = size
                frame = icon.copy().convert("L")
                width, height = frame.size
                edge = (
                    [frame.getpixel((x, 0)) for x in range(width)]
                    + [frame.getpixel((x, height - 1)) for x in range(width)]
                    + [frame.getpixel((0, y)) for y in range(height)]
                    + [frame.getpixel((width - 1, y)) for y in range(height)]
                )
                dark = sum(1 for value in edge if value < 128)
                assert dark > len(edge) * 0.8, (
                    f"the {width}px frame is missing or too faint "
                    f"({dark} of {len(edge)} edge pixels are dark)"
                )

    def test_it_is_black_on_white(self):
        """Not a check of taste: an icon that came out mostly transparent, or
        inverted, still opens and still looks like a file.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.PNG) as png:
            pixels = list(png.convert("L").getdata())
        white = sum(1 for value in pixels if value > 200)
        black = sum(1 for value in pixels if value < 60)
        assert white > black, "the icon is mostly dark; the background should be white"
        assert black > len(pixels) // 100, "there is almost no ink; is the letter there?"

    def test_the_small_frames_are_uncompressed(self):
        """DIB below 256 pixels, PNG only for the 256.

        Windows has accepted PNG-compressed frames since Vista, but the format
        every icon editor produces — and the one the shell has always read —
        is an uncompressed DIB at the small sizes. Explorer showing a stale or
        generic icon for an executable whose resources are demonstrably
        correct is exactly the shape of problem that convention avoids.
        """
        import struct

        data = self.ICO.read_bytes()
        _, _, count = struct.unpack("<HHH", data[:6])
        png_magic = b"\x89PNG\r\n\x1a\x0a"
        for index in range(count):
            entry = 6 + index * 16
            width, _h, _c, _r, _p, _b, size, offset = struct.unpack(
                "<BBBBHHII", data[entry:entry + 16]
            )
            width = width or 256
            is_png = data[offset:offset + 8] == png_magic
            if width >= 256:
                assert is_png, "the 256 frame should be PNG; it is the one worth compressing"
            else:
                assert not is_png, f"the {width}px frame is PNG-compressed"

    def test_every_frame_reads_back_at_its_declared_size(self):
        """The .ico is assembled by hand, so a wrong header length or a
        bottom-up row order would produce a file that still opens and is
        quietly wrong.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.ICO) as icon:
            sizes = sorted(icon.info["sizes"])
            for size in sizes:
                icon.size = size
                frame = icon.copy().convert("L")
                pixels = list(frame.get_flattened_data()
                              if hasattr(frame, "get_flattened_data") else frame.getdata())
                assert len(pixels) == size[0] * size[1]
                assert any(value < 60 for value in pixels), f"{size[0]}px has no ink"
                assert any(value > 200 for value in pixels), f"{size[0]}px has no ground"

    def test_regenerating_them_reproduces_what_is_committed(self, tmp_path):
        """The committed files are the generator's output, and stay that way.

        This is the check that makes "regenerate and diff" a usable answer to
        "is the icon still the one the script draws". It is also the check that
        would have caught the way the arguments used to work: the letter and
        the file name came from one argument, so the only way to write the
        right file name here was to pass the wrong letter, and doing exactly
        that redrew this product's icons with someone else's initial on them.

        Skipped where the serif face is not installed: the drawing depends on
        it, so on a machine without it the comparison would be measuring the
        font rather than the generator.
        """
        import hashlib
        import subprocess
        import sys

        pytest.importorskip("PIL", reason="Pillow draws the icons")
        sys.path.insert(0, str(REPO / "tools"))
        try:
            import make_icon
        finally:
            sys.path.pop(0)
        # Not "some candidate exists": the committed files were drawn with
        # Liberation Serif, and a Windows runner resolves the next candidate --
        # real Times New Roman -- which is metric-compatible but not the same
        # outlines. The comparison would then be measuring the font.
        chosen = next(
            (p for p in make_icon.FONT_CANDIDATES if pathlib.Path(p).exists()), None
        )
        if chosen is None or "Liberation" not in chosen:
            pytest.skip(f"drawn with {chosen or 'no serif font'}, not Liberation Serif")

        run = subprocess.run(
            [sys.executable, str(REPO / "tools" / "make_icon.py"),
             "Tyche", str(tmp_path), "app_icon"],
            capture_output=True, text=True,
        )
        assert run.returncode == 0, run.stderr

        for suffix in (".png", ".ico", ".icns"):
            committed = REPO / "assets" / f"app_icon{suffix}"
            if not committed.exists():
                # The generator writes all three for everybody; only the
                # products that build a macOS application bundle have any
                # use for the .icns, and the rest do not carry one.
                assert suffix == ".icns", f"{committed.name} is missing"
                continue
            fresh = (tmp_path / "app_icon").with_suffix(suffix)
            # Compared by digest, not by bytes: an assertion on the
            # contents printed a hundred lines of PNG into the CI log
            # and said nothing a reader could act on.
            assert (
                hashlib.sha256(fresh.read_bytes()).hexdigest()
                == hashlib.sha256(committed.read_bytes()).hexdigest()
            ), f"{committed.name} is not what tools/make_icon.py draws today"

    def test_the_generator_is_kept_with_them(self):
        """So the next one can be drawn the same way rather than guessed at."""
        assert (REPO / "tools" / "make_icon.py").is_file()


class TestWindowIcon:
    """The icon has to reach the window, not merely ship beside it.

    Reported: the executable carried both the .ico and the .png -- verified by
    reading them back out of the published build -- and the window still came
    up under Tk's default feather. The cause was one ``try`` around both
    attempts: ``iconbitmap`` raised, and the fallback that would have set the
    PNG never ran.
    """

    SOURCE = REPO / "gui/app.py"
    FUNCTION = "_set_window_icon"

    def _icon_function(self):
        import ast

        tree = ast.parse(self.SOURCE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == self.FUNCTION:
                return node
        raise AssertionError(f"{self.FUNCTION} is not in {self.SOURCE}")

    def test_it_sets_the_icon_from_both_files(self):
        import ast

        called = {
            node.func.attr
            for node in ast.walk(self._icon_function())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "iconphoto" in called, "nothing sets the icon off Windows"
        assert "iconbitmap" in called, "nothing uses the .ico on Windows"

    def test_one_attempt_failing_does_not_take_the_other_down(self):
        """The bug, stated as a shape: no single ``try`` may hold both calls.

        Tk raises before it changes anything, so the two are safe to attempt
        independently -- and independent is the only way a failure in one
        leaves the other's work standing.
        """
        import ast

        for node in ast.walk(self._icon_function()):
            if not isinstance(node, ast.Try):
                continue
            inside = {
                call.func.attr
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            }
            assert not {"iconphoto", "iconbitmap"} <= inside, (
                "both attempts share one try: a failure in either loses both"
            )

    def test_the_photo_image_is_kept_alive(self):
        """Tk holds only a weak reference to it. A collected PhotoImage
        leaves a blank icon, which looks exactly like never setting one.
        """
        import ast

        assigned = [
            target.attr
            for node in ast.walk(self._icon_function())
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Attribute)
        ]
        assert assigned, "the PhotoImage is not stored anywhere and will be collected"


class TestStartsMaximised:
    """The window opens filling the screen, and knows whether it did.

    The first version stopped at the first call that did not raise. Not
    raising is not the same as having worked: with no window manager running,
    both ``state("zoomed")`` and the ``-zoomed`` attribute are accepted in
    silence and change nothing, and the chain never reaches the one that
    would have worked.
    """

    def _maximise_source(self) -> str:
        import ast

        source = (REPO / "gui" / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_maximize":
                return ast.get_source_segment(source, node) or ""
        raise AssertionError("_maximize is not in gui/app.py")

    def test_it_checks_whether_the_window_actually_grew(self):
        body = self._maximise_source()
        assert "winfo_width" in body and "winfo_screenwidth" in body, (
            "nothing measures the result; a silent no-op would count as success"
        )

    def test_it_tries_every_way_before_giving_up(self):
        body = self._maximise_source()
        for way in ("zoomed", "-zoomed", "winfo_screenheight"):
            assert way in body, f"the {way} attempt is missing"

    def test_it_is_called_at_start_up(self):
        source = (REPO / "gui" / "app.py").read_text(encoding="utf-8")
        assert "self._maximize" in source.split("def _maximize", 1)[0], (
            "_maximize is defined but never scheduled"
        )


class TestInterfaceFont:
    """One font across the four, named rather than left to a default.

    Arial was hard-coded in the other two products — nowhere else — which is what made those
    labels the odd ones out. Nothing asks for it now, and nothing relies on
    whichever family the toolkit would have picked.
    """

    PREFERENCE = (
        "Segoe UI",
        "SF Pro Text",
        "Helvetica Neue",
        "Noto Sans",
        "DejaVu Sans",
    )

    def test_the_preference_list_is_the_shared_one(self):
        from core.fonts import UI_FONT_PREFERENCE
        assert UI_FONT_PREFERENCE == self.PREFERENCE

    def test_nothing_asks_for_arial(self):
        import re

        for path in sorted(str(p.relative_to(REPO)) for p in (REPO / "gui").glob("*.py")):
            source = (REPO / path).read_text(encoding="utf-8")
            code = "\n".join(
                line for line in source.splitlines()
                if not line.lstrip().startswith("#")
            )
            assert not re.search(r'"Arial"', code), f"{path} still asks for Arial"

    def test_the_family_resolves_to_something_real(self):
        pytest.importorskip("tkinter", reason="the toolkit is not installed here")
        import tkinter as tk

        from core.fonts import ui_font_family
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            pytest.skip(f"no display: {exc}")
        try:
            from tkinter import font as tkfont

            family = ui_font_family()
            assert family, "no family was resolved"
            # Either one of ours, or the one Tk itself would have used — never
            # a name the system will silently substitute for something else.
            assert (family in self.PREFERENCE
                    or family == tkfont.nametofont("TkDefaultFont").actual("family"))
        finally:
            root.destroy()


class TestLicenceHeader:
    """Every source file opens with the same seven lines.

    A file copied out of this repository has to say what it is and what may be
    done with it, which is the whole reason the header exists. That it is
    *present* was checked when it was added; that it is still one unbroken
    block at the top was not — and in one of these products an automated edit
    inserted an import between the product name and the copyright line, where
    it sat unnoticed because every check only looked for the SPDX line
    somewhere in the file.
    """

    #: The shape, not the wording: the product line differs per repository and
    #: the year will move.
    SHAPE = (
        "# Tyche",
        "# Copyright (C)",
        "#",
        "# SPDX-License-Identifier: AGPL-3.0-or-later",
        "# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.",
    )

    def sources(self):
        for root in ("core", "gui", "tests", "tools"):
            for path in sorted((REPO / root).rglob("*.py")):
                if "__pycache__" in path.parts or ".venv" in path.parts:
                    continue
                yield path

    def test_there_is_something_to_check(self):
        assert list(self.sources()), "no source files found; the roots are wrong"

    def test_every_file_opens_with_the_unbroken_header(self):
        wrong = []
        for path in self.sources():
            lines = path.read_text(encoding="utf-8").splitlines()
            # A shebang, where a file has one, stays on the first line.
            if lines and lines[0].startswith("#!"):
                lines = lines[1:]
            for offset, expected in enumerate(self.SHAPE):
                if offset >= len(lines) or not lines[offset].startswith(expected):
                    got = lines[offset] if offset < len(lines) else "<end of file>"
                    wrong.append(
                        f"{path.relative_to(REPO)} line {offset + 1}: "
                        f"expected {expected!r}, found {got!r}"
                    )
                    break
        assert not wrong, "the licence header is broken in:\n  " + "\n  ".join(wrong)
