# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
statistics_panel.py — Tyche

The frequency, gap, decade and pair tables — the four screens every lottery
site sells a system on top of, with the expected value printed in the same row
as the observed one.
"""

from __future__ import annotations

import customtkinter as ctk

from core.statistics import decade_table, number_table, summary_lines, top_pairs
from gui.theme import BG_ROOT, MUTED
from gui.widgets import ReportBox, section


class StatisticsPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._build()

    def _build(self) -> None:
        head = section(self, "The archive in numbers")
        head.pack(fill="x", padx=16, pady=(16, 8))
        self.summary = ctk.CTkLabel(
            head.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=1000
        )
        self.summary.pack(fill="x")

        self.tabs = ctk.CTkTabview(self, fg_color=BG_ROOT)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        for name in ("Frequency & gaps", "Bands of ten", "Pairs"):
            self.tabs.add(name)
        self.freq_box = ReportBox(self.tabs.tab("Frequency & gaps"), height=420)
        self.freq_box.pack(fill="both", expand=True)
        self.decade_box = ReportBox(self.tabs.tab("Bands of ten"), height=420)
        self.decade_box.pack(fill="both", expand=True)
        self.pairs_box = ReportBox(self.tabs.tab("Pairs"), height=420)
        self.pairs_box.pack(fill="both", expand=True)

    def refresh(self) -> None:
        draws = self.app.draws
        self.summary.configure(text="\n".join(summary_lines(draws)))
        if not draws:
            for box in (self.freq_box, self.decade_box, self.pairs_box):
                box.set_text("")
            return

        rows = number_table(draws)
        header = (
            f"{'n':>3} {'drawn':>6} {'expected':>9} {'σ':>7}  "
            f"{'gap':>5} {'exp gap':>8}  {'last seen':<12}"
        )
        lines = [header, "─" * len(header)]
        for r in rows:
            flag = "  <" if r.unusual else ""
            lines.append(
                f"{r.number:>3} {r.count:>6} {r.expected:>9.1f} {r.sigma:>+7.2f}  "
                f"{r.gap:>5} {r.expected_gap:>8.1f}  {r.last_seen:<12}{flag}"
            )
        flagged = sum(1 for r in rows if r.unusual)
        lines += [
            "",
            f"{flagged} of 90 numbers are more than two standard deviations from their",
            "expected count, marked '<'. Between four and five is what independent draws",
            "produce: 5% of ninety numbers is 4.5. A table with no flags at all would be",
            "the surprising one.",
        ]
        self.freq_box.set_text("\n".join(lines))

        header = f"{'band':<8} {'observed':>9} {'expected':>9} {'ratio':>7}"
        lines = [header, "─" * len(header)]
        for label, observed, expected, ratio in decade_table(draws):
            lines.append(f"{label:<8} {observed:>9} {expected:>9.1f} {ratio:>7.3f}")
        lines += [
            "",
            "Nine bands of exactly ten numbers, so the expectations are equal and the",
            "ratios compare directly. Drawing the bands as 1–9, 10–19, … 80–90 instead —",
            "which is common — gives a nine-number band and an eleven-number one, and the",
            "eighties then look permanently hot for no reason but their width.",
        ]
        self.decade_box.set_text("\n".join(lines))

        pairs = top_pairs(draws, 25)
        header = f"{'pair':<9} {'together':>9} {'expected':>9}"
        lines = [header, "─" * len(header)]
        for a, b, observed, expected in pairs:
            lines.append(f"{a:>2}–{b:<6} {observed:>9} {expected:>9.1f}")
        lines += [
            "",
            "4,005 pairs are competing for this list, so the top of it is the maximum of",
            "four thousand roughly-Poisson counts and sits several standard deviations",
            "above the mean by construction. This table has no predictive content; it is",
            "here because leaving it out invites the question of what it would have shown.",
        ]
        self.pairs_box.set_text("\n".join(lines))
