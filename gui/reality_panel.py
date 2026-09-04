# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
reality_panel.py — Tyche

The five independence tests from :mod:`core.randomness`.

This is the tab that decides what the rest of the application means, which is
why it opens first on a fresh install. If these tests failed, the forecaster
would be worth running; they do not, so it is worth understanding instead.
"""

from __future__ import annotations

import customtkinter as ctk

from core.randomness import run_all, summarise
from gui.theme import BG_ROOT, GOOD, MUTED, WARN
from gui.widgets import ReportBox, section


class RealityPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._build()

    def _build(self) -> None:
        head = section(
            self, "Is there anything to predict?",
            "Five tests of the hypothesis that the archive is independent uniform draws. "
            "A small p-value would mean the draw machinery is biased and something here "
            "is exploitable. A large one means the game is fair, and that no forecast can "
            "beat chance — including the one this program makes.",
        )
        head.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkButton(head.body, text="Run the tests", width=160,
                      command=self.run_tests).pack(anchor="w")
        self.verdict = ctk.CTkLabel(
            head.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=1000
        )
        self.verdict.pack(fill="x", pady=(10, 0))

        body = section(self, "Results")
        body.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.box = ReportBox(body.body, height=380)
        self.box.pack(fill="both", expand=True)

    def run_tests(self) -> None:
        draws = self.app.draws
        if not draws:
            self.box.set_text("The archive is empty. Fetch it from the Archive tab first.")
            return
        results = run_all(draws)
        lines = []
        for r in results:
            lines.append(r.name)
            stat = f"χ² = {r.statistic:.3f}, dof {r.dof}" if r.dof else f"z = {r.statistic:+.3f}"
            lines.append(f"    {stat}")
            lines.append(f"    {r.verdict}")
            if r.detail:
                lines.append(f"    {r.detail}")
            lines.append("")
        self.box.set_text("\n".join(lines))
        text = summarise(results)
        flagged = any(r.significant for r in results)
        self.verdict.configure(text=text, text_color=WARN if flagged else GOOD)

    def refresh(self) -> None:
        # Deliberately not automatic: the tests take a second on a full archive
        # and re-running them on every tab switch would make the whole app feel
        # slow for a result that only changes when the archive does.
        pass
