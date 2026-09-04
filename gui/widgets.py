# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

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

import customtkinter as ctk

from gui.theme import ACCENT, BG_PANEL, BG_ROOT, MUTED, TEXT


def section(parent, title: str, subtitle: str = "") -> ctk.CTkFrame:
    """A titled block. Returns the frame callers put their content in."""
    wrapper = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=8)
    header = ctk.CTkLabel(
        wrapper, text=title, anchor="w", text_color=TEXT,
        font=ctk.CTkFont(size=15, weight="bold"),
    )
    header.pack(fill="x", padx=14, pady=(12, 0))
    if subtitle:
        ctk.CTkLabel(
            wrapper, text=subtitle, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=12), wraplength=900,
        ).pack(fill="x", padx=14, pady=(2, 0))
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

    def __init__(self, parent, height: int = 300, **kwargs):
        super().__init__(
            parent, height=height, fg_color=BG_ROOT, text_color=TEXT,
            font=ctk.CTkFont(family="monospace", size=12),
            wrap="none", **kwargs,
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
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left", padx=3)
    return row
