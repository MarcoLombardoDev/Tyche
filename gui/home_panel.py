# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
home_panel.py — Tyche

The guided path: four numbered steps from an empty archive to six numbers.

Why this panel exists
---------------------

Every other panel explained itself well and none of them explained the
*order*. Six independent tabs, each a competent screen, and nothing saying
which one to open first, what depends on what, or where the thing the user
came for actually is. The owner's verdict on the built application was that
it was incomprehensible — not that any single screen was wrong, but that the
sequence was invisible.

So this is a map, not a new feature. It owns no analysis of its own: every
step points at the panel that does the work, and reports what that panel last
produced. Adding work here would give two places to run the same thing and no
rule about which one counts.

The order is the argument
-------------------------

The steps run archive, fairness, validation, prediction, and that is
deliberately the order in which the answers stop mattering. Step 2 says the
draws are independent; step 3 says no method beats chance; step 4 hands over
six numbers anyway, because that is what the program is for. A user who walks
the path reaches the combinations having already been told what they are
worth, which is a better place to say it than a tab they might never open.

That is also why the path does not skip to the end. Tyche's design note is
that the measurement is the point and the prediction is its demonstration;
the owner's instruction is that the prediction is the purpose. Both are
satisfied by a route that leads to the combinations and passes through the
evidence on the way — and neither would be by hiding one or the other.
"""

from __future__ import annotations

import customtkinter as ctk

from core.archive import describe_archive, freshness
from core.localise import it_date, it_number
from gui.theme import (
    ACCENT,
    BG_PANEL,
    BG_ROOT,
    BG_ROW,
    GOOD,
    MUTED,
    TEXT,
    WARN,
)

# (key of the panel it opens, number, title, the question it answers)
STEPS = [
    ("archive", "1", "Porta i dati",
     "Serve lo storico delle estrazioni. Senza, non c'è niente da analizzare."),
    ("reality", "2", "Guarda se c'è qualcosa da prevedere",
     "Cinque test dicono se le estrazioni sono davvero indipendenti e uniformi, "
     "cioè se esiste una struttura da sfruttare."),
    ("validation", "3", "Metti alla prova i metodi",
     "Ogni metodo viene fatto girare sulle estrazioni passate, vedendo solo il "
     "passato, e confrontato con il caso."),
    ("prediction", "4", "Genera le combinazioni",
     "Il punto di arrivo: sei numeri, con accanto quello che i passi precedenti "
     "hanno stabilito che valgono."),
]


class HomePanel(ctk.CTkFrame):
    """Four steps, their current state, and a way into each."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._state_labels: dict[str, ctk.CTkLabel] = {}
        self._marks: dict[str, ctk.CTkLabel] = {}
        self._build()

    # ── layout ───────────────────────────────────────────────
    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=8)
        head.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            head, text="Che cosa fa Tyche", anchor="w", text_color=TEXT,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(fill="x", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            head,
            text=(
                "Scarica lo storico del SuperEnalotto dal 1997, verifica se contiene "
                "una struttura sfruttabile, mette alla prova ogni metodo di previsione "
                "sulle estrazioni già avvenute e infine genera delle combinazioni.\n"
                "Segui i quattro passi qui sotto nell'ordine: ognuno risponde a una "
                "domanda e prepara il successivo."
            ),
            anchor="w", justify="left", text_color=MUTED, wraplength=1080,
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", padx=16, pady=(0, 14))

        for key, number, title, description in STEPS:
            self._step_card(key, number, title, description)

        extra = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=8)
        extra.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkLabel(
            extra, text="Fuori percorso", anchor="w", text_color=TEXT,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(fill="x", padx=16, pady=(12, 2))
        row = ctk.CTkFrame(extra, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkLabel(
            row,
            text=(
                "Statistiche — l'archivio in cifre, numero per numero. "
                "Impostazioni — modello, token e sorgenti."
            ),
            anchor="w", justify="left", text_color=MUTED, wraplength=760,
            font=ctk.CTkFont(size=12),
        ).pack(side="left")
        ctk.CTkButton(
            row, text="Statistiche", width=120, fg_color=BG_ROW, text_color=TEXT,
            command=lambda: self.app.show("statistics"),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            row, text="Impostazioni", width=120, fg_color=BG_ROW, text_color=TEXT,
            command=lambda: self.app.show("settings"),
        ).pack(side="right")

    def _step_card(self, key: str, number: str, title: str, description: str) -> None:
        card = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=8)
        card.pack(fill="x", padx=16, pady=3)

        # The number goes straight into the card. Wrapping it in a frame with
        # pack_propagate(False) — the obvious way to fix its width — pins that
        # frame at CTkFrame's default 200px height, which made every card 200px
        # tall and pushed step 4, the destination, below the fold.
        ctk.CTkLabel(
            card, text=number, width=42, text_color=ACCENT,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left", padx=(16, 0), pady=(10, 0), anchor="n")

        middle = ctk.CTkFrame(card, fg_color="transparent")
        middle.pack(side="left", fill="both", expand=True, pady=10)
        ctk.CTkLabel(
            middle, text=title, anchor="w", text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(fill="x")
        ctk.CTkLabel(
            middle, text=description, anchor="w", justify="left",
            text_color=MUTED, wraplength=780, font=ctk.CTkFont(size=12),
        ).pack(fill="x", pady=(1, 0))
        # What this step has actually produced, filled in by refresh().
        state = ctk.CTkLabel(
            middle, text="", anchor="w", justify="left", text_color=MUTED,
            wraplength=780, font=ctk.CTkFont(size=12),
        )
        state.pack(fill="x", pady=(4, 0))
        self._state_labels[key] = state

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="right", padx=16, pady=10)
        mark = ctk.CTkLabel(
            right, text="", text_color=MUTED, font=ctk.CTkFont(size=18, weight="bold")
        )
        mark.pack(anchor="e", pady=(0, 2))
        self._marks[key] = mark
        ctk.CTkButton(
            right, text="Vai", width=110,
            command=lambda k=key: self.app.show(k),
        ).pack(anchor="e", pady=(6, 0))

    # ── state ────────────────────────────────────────────────
    def refresh(self) -> None:
        """Re-read what each step has produced. Called on every tab switch."""
        for key, (text, colour, mark) in self._states().items():
            self._state_labels[key].configure(text=text, text_color=colour)
            self._marks[key].configure(text=mark, text_color=colour)

    def _states(self) -> dict[str, tuple[str, str, str]]:
        """``{step: (state text, colour, mark)}`` for the four steps.

        Kept as one function returning plain data so the smoke tests can read
        the same answers the labels show, rather than scraping widgets.
        """
        return {
            "archive": self._archive_state(),
            "reality": self._reality_state(),
            "validation": self._validation_state(),
            "prediction": self._prediction_state(),
        }

    def _archive_state(self) -> tuple[str, str, str]:
        draws = self.app.draws
        if not draws:
            return ("Nessun archivio. Apri il passo 1 e scaricalo: è una richiesta "
                    "sola.", WARN, "!")
        info = describe_archive(draws)
        summary = (
            f"{it_number(info['count'])} estrazioni, dal {it_date(info['first'])} "
            f"al {it_date(info['last'])}."
        )
        state = freshness(draws)
        if state.stale:
            return (
                f"{summary} Mancano circa {it_number(state.estimated_missing)} "
                "estrazioni: aggiornalo prima di fidarti dei numeri qui sotto.",
                WARN, "!",
            )
        return (f"{summary} Aggiornato.", GOOD, "✓")

    def _reality_state(self) -> tuple[str, str, str]:
        results = getattr(self.app, "last_reality", None)
        if not self.app.draws:
            return ("Serve prima l'archivio.", MUTED, "·")
        if not results:
            return ("Non ancora eseguito.", MUTED, "·")
        flagged = [r for r in results if r.significant]
        if not flagged:
            return (
                f"Eseguito: tutti e {len(results)} i test sono compatibili con "
                "estrazioni indipendenti. Non c'è struttura da sfruttare.",
                GOOD, "✓",
            )
        names = ", ".join(r.name for r in flagged)
        return (
            f"Eseguito: {len(flagged)} test su {len(results)} si discosta "
            f"({names}). Leggi la scheda prima di trarne qualcosa.",
            WARN, "✓",
        )

    def _validation_state(self) -> tuple[str, str, str]:
        report = getattr(self.app, "last_validation", None)
        if not self.app.draws:
            return ("Serve prima l'archivio.", MUTED, "·")
        if not report or not report.results:
            return ("Non ancora eseguito.", MUTED, "·")
        best = report.best()
        beat = [r for r in report.results if r.p_value < 0.05 and r.z > 0]
        if not beat:
            return (
                f"Eseguito su {it_number(report.draws_scored)} estrazioni: nessun "
                f"metodo batte il caso. Il migliore è {best.method} con "
                f"{best.mean_hits:.4f} centri per estrazione, contro "
                f"{best.expected_mean:.4f} del caso.",
                GOOD, "✓",
            )
        return (
            f"Eseguito su {it_number(report.draws_scored)} estrazioni: "
            f"{len(beat)} metodo/i sopra il caso al 5%. Ripeti la prova su una "
            "porzione diversa prima di considerarlo un risultato.",
            WARN, "✓",
        )

    def _prediction_state(self) -> tuple[str, str, str]:
        prediction = getattr(self.app, "last_prediction", None)
        if not self.app.draws:
            return ("Serve prima l'archivio.", MUTED, "·")
        if not prediction:
            return (
                "Non ancora generate. Qualunque metodo scegli, il punteggio atteso "
                "è lo stesso: 0,4 numeri indovinati su sei.",
                MUTED, "·",
            )
        return (
            f"{len(prediction.combinations)} combinazioni generate con "
            f"«{prediction.method}».",
            GOOD, "✓",
        )
