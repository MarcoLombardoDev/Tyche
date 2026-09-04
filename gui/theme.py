# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
theme.py — Tyche

Colours and the dark ttk scrollbar, in one module so a panel never hardcodes
a hex value.

``ttk.Scrollbar`` is a native widget and CustomTkinter does not theme it, so
without :func:`dark_scrollbar` every scrolling panel gets a light grey bar
against a near-black background. Argus hit this and solved it the same way;
the style names differ so the two applications can share a process during
testing without fighting over the registry.
"""

from __future__ import annotations

import contextlib
from tkinter import ttk

BG_ROOT = "#16181d"
BG_PANEL = "#1e2229"
BG_INPUT = "#272c35"
BG_ROW = "#232830"
ACCENT = "#7c5cff"        # Tyche's own colour; Argus uses Binance yellow
ACCENT_HOVER = "#6a4ce0"
TEXT = "#e6e8ec"
MUTED = "#8b93a7"
SEP = "#333a45"
GOOD = "#3fb950"
WARN = "#d9a441"
BAD = "#e5534b"

SCROLLBAR_V = "Tyche.Vertical.TScrollbar"
SCROLLBAR_H = "Tyche.Horizontal.TScrollbar"


def setup_scrollbar_style() -> None:
    """Register the dark scrollbar styles. Idempotent, and never raises.

    The ``clam`` theme is requested because the default themes on Windows and
    macOS ignore most colour options on a scrollbar; if it is unavailable the
    bar is merely ugly, which is not worth an exception on startup.
    """
    style = ttk.Style()
    with contextlib.suppress(Exception):
        style.theme_use("clam")
    for name, orient in ((SCROLLBAR_V, "vertical"), (SCROLLBAR_H, "horizontal")):
        options = {
            "troughcolor": BG_ROOT,
            "background": SEP,
            "bordercolor": BG_ROOT,
            "arrowcolor": MUTED,
            "darkcolor": BG_ROOT,
            "lightcolor": BG_ROOT,
            "relief": "flat",
            "borderwidth": 0,
        }
        if orient == "vertical":
            # width is only meaningful on the vertical bar, and passing it as
            # None raises TclError rather than being ignored.
            options["width"] = 12
        with contextlib.suppress(Exception):
            style.configure(name, **options)
            style.map(
                name,
                background=[("active", "#4a5364"), ("pressed", "#4a5364")],
                arrowcolor=[("active", TEXT)],
            )


def dark_scrollbar(parent, orient: str, command) -> ttk.Scrollbar:
    setup_scrollbar_style()
    return ttk.Scrollbar(
        parent, orient=orient, command=command,
        style=SCROLLBAR_V if orient == "vertical" else SCROLLBAR_H,
    )
