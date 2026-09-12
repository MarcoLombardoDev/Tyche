# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
widgets.py — Tyche

The three composite widgets more than one panel needs: a section heading, a
fixed-width text report, and the ball row that renders a combination.

They live here rather than in a base class because the panels are otherwise
independent, and a shared base class for five screens that have nothing in
common but a background colour is the kind of inheritance that has to be
undone later.
"""

from __future__ import annotations

import math
import tkinter

import customtkinter as ctk

from core.fonts import ui_font_family
from gui.theme import ACCENT, BG_PANEL, BG_ROOT, MUTED, TEXT

# One size for everything a user reads, and two exceptions with a reason:
# buttons, which CustomTkinter sizes itself, and headings, which are bold.
# Before 1.0.0 the labels ran 11, 12, 13 and the CustomTkinter default all on
# one screen, because a label with no `font=` silently takes the toolkit's,
# and the result read as four different kinds of text saying the same kind of
# thing. `test_every_label_is_one_size_unless_it_is_a_heading` is the guard.
BODY_SIZE = 12
HEADING_SIZE = 15


# Every font this program uses, kept for the life of the process.
#
# **Not an optimisation — a Tk font that gets collected can hang the program.**
# ``tkinter.font.Font.__del__`` calls Tcl (``font delete``), and the garbage
# collector runs on whichever thread happens to trip the threshold. When that
# thread is a worker, the call goes into Tcl from outside the Tk thread and
# blocks there: the forecast stops mid-way, the status bar keeps the last
# method it announced, and the button never comes back. See
# ``TycheApp.run_worker`` for the other half of the defence.
#
# Building one CTkFont per label made hundreds of collectable Tk objects per
# screen. Caching them means there is almost nothing left to collect.
_FONTS: dict[tuple, ctk.CTkFont] = {}


def reset_fonts() -> None:
    """Drop the cache. Called when a window is built, and it has to be.

    **A Tk font belongs to the interpreter that created it.** The cache is a
    module global and outlives a window, so without this the second window in
    a process — which is every test after the first — hands its labels fonts
    belonging to a destroyed application, and the next ``cget`` raises
    ``TclError: application has been destroyed``. Caching the fonts without
    this line turned one intermittent failure into a reliable one, which at
    least had the courtesy of being obvious.

    Dropping them runs ``Font.__del__`` here, on the main thread, while a
    window is being built and no worker exists — which is the legal place for
    it, and the whole point of the cache.
    """
    _FONTS.clear()


def _font(size: int, weight: str = "normal"):
    key = (ui_font_family(), size, weight)
    if key not in _FONTS:
        _FONTS[key] = ctk.CTkFont(family=key[0], size=size, weight=weight)
    return _FONTS[key]


def link_font():
    """Underlined body text: the one clickable label in the window."""
    key = (ui_font_family(), BODY_SIZE, "link")
    if key not in _FONTS:
        _FONTS[key] = ctk.CTkFont(
            family=key[0], size=BODY_SIZE, underline=True,
        )
    return _FONTS[key]


def mono_font():
    """The report boxes' font. Monospace on purpose: they hold tables."""
    key = ("monospace", BODY_SIZE, "normal")
    if key not in _FONTS:
        _FONTS[key] = ctk.CTkFont(family="monospace", size=BODY_SIZE)
    return _FONTS[key]


def body_font():
    """The size every non-heading label uses. Pass it, do not default to it."""
    return _font(BODY_SIZE)


def heading_font(size: int = HEADING_SIZE):
    """Bold, and therefore exempt from the one-size rule."""
    return _font(size, "bold")


def fit_text(label, margin: int = 32):
    """Make a label wrap to the window's width instead of a number from 2026.

    Tk labels do not wrap at all without ``wraplength``, and a ``wraplength``
    in pixels is a guess about the window: every panel here carried one — 760,
    780, 1000, 1080 — so on a maximised screen the prose broke less than
    halfway across and left the rest of the row empty.

    **Bound to the toplevel, and measuring the label's parent — not the label.**
    Two earlier versions bound ``<Configure>`` on the label itself and set the
    wraplength from ``event.width``, which oscillates: a narrower wraplength
    makes the label *request* a different width, pack propagation grants some
    of it, and the next Configure sees 621 where the last saw 660, forever.
    That did not fail, it hung — ``update()`` never returned and the whole GUI
    suite stopped dead. The parent's width is imposed by the window above it
    and does not answer back.
    """
    applied = {"width": 0}

    def resize(event=None):
        # The binding lives on the toplevel and outlives the label: a panel
        # destroyed while the window is still up leaves this callback pointing
        # at a widget that is gone. On Linux the ordering happened never to
        # hit it; the Windows leg of CI printed a TclError per orphan on every
        # test that closed a window. Ask, and stand down when the answer is no.
        try:
            if not label.winfo_exists():
                return
            width = label.master.winfo_width()
        except tkinter.TclError:
            return
        if abs(width - applied["width"]) < 4:
            return
        applied["width"] = width
        label.configure(wraplength=max(width - margin, 200))

    # ``add="+"`` because every label bound this way shares the toplevel, and
    # a plain bind would leave only the last one working.
    label.winfo_toplevel().bind("<Configure>", resize, add="+")
    # And once on the way in, so the first frame is right rather than waiting
    # for the user to resize something.
    label.after_idle(resize)
    return label


def section(parent, title: str, subtitle: str = "") -> ctk.CTkFrame:
    """A titled block. Returns the frame callers put their content in."""
    wrapper = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=8)
    header = ctk.CTkLabel(
        wrapper, text=title, anchor="w", text_color=TEXT, font=heading_font(),
    )
    header.pack(fill="x", padx=14, pady=(12, 0))
    if subtitle:
        fit_text(ctk.CTkLabel(
            wrapper, text=subtitle, anchor="w", justify="left", text_color=MUTED,
            font=body_font(), wraplength=900,
        )).pack(fill="x", padx=14, pady=(2, 0))
    body = ctk.CTkFrame(wrapper, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=14, pady=12)
    wrapper.body = body          # type: ignore[attr-defined]
    return wrapper


class ReportBox(ctk.CTkTextbox):
    """A read-only monospaced textbox for tables and test output.

    Read-only is enforced by switching the widget back to ``disabled`` after
    every write rather than by leaving it disabled, because a disabled
    CTkTextbox refuses ``insert`` too. Forgetting the re-enable is the reason
    a panel silently stops updating.
    """

    def __init__(self, parent, height: int = 300, wrap: str = "none", **kwargs):
        # ``wrap="none"`` for tables, which must not be re-flowed; ``"word"``
        # for a box that is mostly prose, so it uses the window's width rather
        # than a column count guessed when the text was written.
        super().__init__(
            parent, height=height, fg_color=BG_ROOT, text_color=TEXT,
            font=mono_font(),
            wrap=wrap, **kwargs,
        )
        self.configure(state="disabled")

    def set_text(self, text: str) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.insert("1.0", text)
        self.configure(state="disabled")


def ball_row(parent, numbers, size: int = 38, per_line: int = 6) -> ctk.CTkFrame:
    """Render a combination as circles, the way a receipt prints it.

    The digits are sized by :func:`badge_font_size`, the same rule the
    SuperStar's star uses, so a ball and a star of the same width carry
    numbers of the same height. Hard-coding 14 here — which is what this did —
    meant the two matched at one size and nowhere else.

    **It wraps, and it has to.** ``pack`` clips what does not fit and says
    nothing: at fifty pixels a *sistema integrale* of twelve numbers ran off
    the side of its cell and showed seven, which is the worst way for this
    screen to be wrong — five numbers the user would be playing, missing, with
    nothing to suggest anything was cut. Six a line, because six is a column:
    a system of nine then reads as a column and three more, which is how the
    ranking builds it.
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    numbers = list(numbers)
    for start in range(0, len(numbers), per_line):
        line = ctk.CTkFrame(row, fg_color="transparent")
        line.pack(fill="x", pady=1)
        for n in numbers[start:start + per_line]:
            ctk.CTkLabel(
                line, text=f"{n:02d}", width=size, height=size,
                corner_radius=size // 2, fg_color=ACCENT, text_color="#ffffff",
                font=_font(badge_font_size(size), "bold"),
            ).pack(side="left", padx=3)
    return row


def badge_font_size(size: int) -> int:
    """How big the number inside a ball or a star of ``size`` pixels is.

    One rule for both, because they sit on the same row and a reader compares
    them: six numbers and a SuperStar have to look like seven numbers, one of
    which is marked, rather than like two kinds of thing.
    """
    return max(11, round(size * 0.28))



# How deep the star's notches cut. A regular pentagram is 0.382, which is
# elegant and leaves a centre too small to put two digits in: the number would
# sit over the points rather than inside the shape. 0.55 is a fatter star —
# still unmistakably a star, with a body that holds "49".
_STAR_INNER = 0.55


def _star_points(centre: float, outer: float, inner: float, points: int = 5) -> list[float]:
    """Flat x,y pairs for a star with one point straight up.

    ``-pi/2`` is what puts that point at the top; without it the polygon comes
    out rotated and reads as a cog.
    """
    coords: list[float] = []
    for index in range(points * 2):
        radius = outer if index % 2 == 0 else inner
        angle = -math.pi / 2 + index * math.pi / points
        coords += [centre + radius * math.cos(angle), centre + radius * math.sin(angle)]
    return coords


def star_badge(parent, number: int, size: int = 42, background: str = BG_PANEL):
    """The SuperStar: its number inside a star in Tyche's own purple.

    **A shape rather than a glyph, and a canvas because CustomTkinter has no
    star.** ``CTkLabel`` draws a rounded rectangle and nothing else, so the
    first version put a ★ character beside an ordinary purple ball — which
    said "this one is the SuperStar" in two pieces where one will do. Tk's
    canvas draws polygons natively, so the badge is a real star with the
    number in the middle of it and no second widget to align.

    ``background`` has to match what the badge sits on: a canvas is opaque and
    a wrong colour here shows as a grey square around the star.
    """
    canvas = ctk.CTkCanvas(
        parent, width=size, height=size, bg=background,
        highlightthickness=0, bd=0,
    )
    centre = size / 2
    canvas.create_polygon(
        _star_points(centre, centre, centre * _STAR_INNER),
        fill=ACCENT, outline="",
    )
    # A point-up star carries more of its area below the centre of its
    # bounding circle, so text placed at the geometric middle reads high. The
    # nudge is small and it is the difference between "in the star" and
    # "floating in it".
    canvas.create_text(
        centre, centre + size * 0.04, text=f"{number:02d}", fill="#ffffff",
        font=(ui_font_family(), badge_font_size(size), "bold"),
    )
    return canvas
