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


def body_font():
    """The size every non-heading label uses. Pass it, do not default to it."""
    return ctk.CTkFont(family=ui_font_family(), size=BODY_SIZE)


def heading_font(size: int = HEADING_SIZE):
    """Bold, and therefore exempt from the one-size rule."""
    return ctk.CTkFont(family=ui_font_family(), size=size, weight="bold")


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
            font=ctk.CTkFont(family="monospace", size=BODY_SIZE),
            wrap=wrap, **kwargs,
        )
        self.configure(state="disabled")

    def set_text(self, text: str) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.insert("1.0", text)
        self.configure(state="disabled")


def ball_row(parent, numbers, size: int = 38) -> ctk.CTkFrame:
    """Render a combination as circles, the way a receipt prints it."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    for n in numbers:
        ctk.CTkLabel(
            row, text=f"{n:02d}", width=size, height=size, corner_radius=size // 2,
            fg_color=ACCENT, text_color="#ffffff",
            font=ctk.CTkFont(family=ui_font_family(), size=14, weight="bold"),
        ).pack(side="left", padx=3)
    return row
