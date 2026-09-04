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
        head = section(self, "L'archivio in cifre")
        head.pack(fill="x", padx=16, pady=(16, 8))
        self.summary = ctk.CTkLabel(
            head.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=1000
        )
        self.summary.pack(fill="x")

        self.tabs = ctk.CTkTabview(self, fg_color=BG_ROOT)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        for name in ("Frequenze e ritardi", "Decine", "Coppie"):
            self.tabs.add(name)
        self.freq_box = ReportBox(self.tabs.tab("Frequenze e ritardi"), height=420)
        self.freq_box.pack(fill="both", expand=True)
        self.decade_box = ReportBox(self.tabs.tab("Decine"), height=420)
        self.decade_box.pack(fill="both", expand=True)
        self.pairs_box = ReportBox(self.tabs.tab("Coppie"), height=420)
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
            f"{'n':>3} {'uscite':>7} {'attese':>7} {'σ':>7}  "
            f"{'rit.':>5} {'rit.atteso':>11}  {'ultima':<12}"
        )
        lines = [header, "─" * len(header)]
        for r in rows:
            flag = "  <" if r.unusual else ""
            lines.append(
                f"{r.number:>3} {r.count:>7} {r.expected:>7.1f} {r.sigma:>+7.2f}  "
                f"{r.gap:>5} {r.expected_gap:>11.1f}  {r.last_seen:<12}{flag}"
            )
        flagged = sum(1 for r in rows if r.unusual)
        lines += [
            "",
            f"{flagged} numeri su 90 distano più di due scarti tipo dalla loro uscita",
            "attesa, segnati con '<'. Fra quattro e cinque è quanto producono estrazioni",
            "indipendenti: il 5% di novanta numeri fa 4,5. Una tabella senza nessun",
            "segno sarebbe quella sorprendente.",
        ]
        self.freq_box.set_text("\n".join(lines))

        header = f"{'decina':<8} {'osservate':>10} {'attese':>9} {'rapporto':>9}"
        lines = [header, "─" * len(header)]
        for label, observed, expected, ratio in decade_table(draws):
            lines.append(f"{label:<8} {observed:>10} {expected:>9.1f} {ratio:>9.3f}")
        lines += [
            "",
            "Nove decine da esattamente dieci numeri, quindi le attese sono uguali e i",
            "rapporti si confrontano direttamente. Tracciare le fasce come 1–9, 10–19,",
            "… 80–90 — come si fa spesso — dà una fascia da nove numeri e una da undici,",
            "e gli ottanta sembrano allora sempre caldi solo per la loro ampiezza.",
        ]
        self.decade_box.set_text("\n".join(lines))

        pairs = top_pairs(draws, 25)
        header = f"{'coppia':<9} {'insieme':>9} {'attese':>9}"
        lines = [header, "─" * len(header)]
        for a, b, observed, expected in pairs:
            lines.append(f"{a:>2}–{b:<6} {observed:>9} {expected:>9.1f}")
        lines += [
            "",
            "Sono 4.005 le coppie in gara per questa lista, quindi la cima è il massimo",
            "di quattromila conteggi grosso modo poissoniani e sta per costruzione a",
            "diversi scarti tipo sopra la media. Questa tabella non ha contenuto",
            "predittivo: è qui perché ometterla farebbe nascere la domanda su che cosa",
            "avrebbe mostrato.",
        ]
        self.pairs_box.set_text("\n".join(lines))
