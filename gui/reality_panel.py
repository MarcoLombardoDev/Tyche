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
            self, "Passo 2 di 4 · C'è qualcosa da prevedere?",
            "Cinque test dell'ipotesi che l'archivio sia fatto di estrazioni indipendenti "
            "e uniformi. Un p-value piccolo direbbe che il meccanismo di estrazione è "
            "sbilanciato e che qui c'è qualcosa di sfruttabile. Uno grande dice che il "
            "gioco è equo, e che nessuna previsione può battere il caso — compresa "
            "quella che fa questo programma.\n"
            "Premi «Esegui i test». Poi vai al passo 3, Validazione, che mette alla "
            "prova i metodi uno per uno.",
        )
        head.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkButton(head.body, text="Esegui i test", width=180,
                      command=self.run_tests).pack(anchor="w")
        self.verdict = ctk.CTkLabel(
            head.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=1000
        )
        self.verdict.pack(fill="x", pady=(10, 0))

        body = section(self, "Risultati")
        body.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.box = ReportBox(body.body, height=380)
        self.box.pack(fill="both", expand=True)

    def run_tests(self) -> None:
        draws = self.app.draws
        if not draws:
            self.box.set_text(
                "L'archivio è vuoto. Scaricalo prima dalla scheda Archivio."
            )
            return
        results = run_all(draws)
        lines = []
        for r in results:
            lines.append(r.name)
            stat = f"χ² = {r.statistic:.3f}, {r.dof} gdl" if r.dof else f"z = {r.statistic:+.3f}"
            lines.append(f"    {stat}")
            lines.append(f"    {r.verdict}")
            if r.detail:
                lines.append(f"    {r.detail}")
            lines.append("")
        self.box.set_text("\n".join(lines))
        text = summarise(results)
        flagged = any(r.significant for r in results)
        self.verdict.configure(text=text, text_color=WARN if flagged else GOOD)
        # The path panel reports what each step produced; this is step 2's.
        self.app.last_reality = results

    def refresh(self) -> None:
        # Deliberately not automatic: the tests take a second on a full archive
        # and re-running them on every tab switch would make the whole app feel
        # slow for a result that only changes when the archive does.
        pass
