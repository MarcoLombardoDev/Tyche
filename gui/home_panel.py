# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
home_panel.py — Tyche

The path: three things that have to be true before six numbers appear.

Why this panel exists
---------------------

Every other panel explained itself well and none of them explained the
*order*. Independent tabs, each a competent screen, and nothing saying which
one to open first, what depends on what, or where the thing the user came for
actually is. The owner's verdict on the built application was that it was
incomprehensible — not that any single screen was wrong, but that the sequence
was invisible.

So this is a map, not a new feature. It owns no analysis: every step points at
the panel that does the work and reports what that panel last produced.

Three steps, not four
---------------------

Until 0.10.0 the path ran archive → fairness → validation → prediction, and
the two middle steps were the evidence: the independence tests, and the
walk-forward backtest measuring every method against chance. The owner could
not follow either of them and asked for both to go.

What replaced them is not a shorter version of the same argument, it is a
different one. The steps are now the three things that must be *true* before a
forecast can run — the archive is current, the model is on disk, then generate
— which is a checklist rather than a case. The case moved to where it cannot
be skipped: the Prediction panel runs all four methods at once and puts the
random control beside TimesFM at the same size, every time, so the reader sees
them disagree without having to open anything.

The measurement itself did not go away, it left the window: ``--validate`` and
``--power`` still run the backtest and its calibration from the command line,
and the README's central claim is still checkable. Do not quietly drop those
too; a claim nobody can re-run is a slogan.
"""

from __future__ import annotations

import customtkinter as ctk

from core.archive import describe_archive, freshness
from core.localise import it_count, it_date, it_number
from core.model_store import availability
from core.version import DEFAULT_TIMESFM_CHECKPOINT
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
from gui.widgets import body_font, fit_text, heading_font

# (key, number, title, what the step is for, the button's label)
STEPS = [
    ("archive", "1", "L'archivio",
     "Lo storico delle estrazioni dal 1997. Senza, non c'è niente da elaborare; "
     "se è indietro, i numeri qui dentro descrivono un altro anno.",
     "Vai all'archivio"),
    ("model", "2", "Il modello TimesFM",
     "Circa 1,3 GB di pesi, scaricati una volta sola e poi eseguiti sul tuo "
     "computer. Senza, restano gli altri tre metodi.",
     "Scarica il modello"),
    ("prediction", "3", "La previsione",
     "Il punto di arrivo: tutti e quattro i metodi, uno accanto all'altro, con "
     "quanto costa la giocata e quanto vale.",
     "Genera le combinazioni"),
]


class HomePanel(ctk.CTkFrame):
    """Three steps, their current state, and a way into each."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._state_labels: dict[str, ctk.CTkLabel] = {}
        self._marks: dict[str, ctk.CTkLabel] = {}
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._build()

    # ── layout ───────────────────────────────────────────────
    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=8)
        head.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            head, text="Che cosa fa Tyche", anchor="w", text_color=TEXT,
            font=heading_font(16),
        ).pack(fill="x", padx=16, pady=(14, 2))
        fit_text(ctk.CTkLabel(
            head,
            text=(
                "Scarica lo storico del SuperEnalotto dal 1997 e genera delle "
                "combinazioni con quattro metodi diversi, mostrandoli affiancati.\n"
                "Uno dei quattro è un generatore casuale, ed è lì di proposito: "
                "hanno tutti lo stesso punteggio atteso, 0,4 numeri indovinati su "
                "sei, perché l'estrazione da prevedere non dipende da niente di ciò "
                "che guardano.\n"
                "I tre passi qui sotto sono le condizioni: archivio aggiornato, "
                "modello scaricato, e poi la previsione."
            ),
            anchor="w", justify="left", text_color=MUTED, wraplength=1080,
            font=body_font(),
        )).pack(fill="x", padx=16, pady=(0, 14))

        for key, number, title, description, action in STEPS:
            self._step_card(key, number, title, description, action)

        extra = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=8)
        extra.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkLabel(
            extra, text="Fuori percorso", anchor="w", text_color=TEXT,
            font=heading_font(13),
        ).pack(fill="x", padx=16, pady=(12, 2))
        row = ctk.CTkFrame(extra, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkButton(
            row, text="Impostazioni", width=140, fg_color=BG_ROW, text_color=TEXT,
            command=lambda: self.app.show("settings"),
        ).pack(side="right")
        fit_text(ctk.CTkLabel(
            row,
            text=(
                "Impostazioni — modello, token, numeri per combinazione, SuperStar "
                "e prezzi. L'archivio in cifre, numero per numero, sta nella scheda "
                "Archivio."
            ),
            anchor="w", justify="left", text_color=MUTED, font=body_font(),
        )).pack(side="left", fill="x", expand=True)

    def _step_card(
        self, key: str, number: str, title: str, description: str, action: str
    ) -> None:
        card = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=8)
        card.pack(fill="x", padx=16, pady=4)

        # The number goes straight into the card. Wrapping it in a frame with
        # pack_propagate(False) — the obvious way to fix its width — pins that
        # frame at CTkFrame's default 200px height, which made every card 200px
        # tall and pushed the last step, the destination, below the fold.
        ctk.CTkLabel(
            card, text=number, width=42, text_color=ACCENT,
            font=heading_font(22),
        ).pack(side="left", padx=(16, 0), pady=(12, 0), anchor="n")

        middle = ctk.CTkFrame(card, fg_color="transparent")
        middle.pack(side="left", fill="both", expand=True, pady=12)
        ctk.CTkLabel(
            middle, text=title, anchor="w", text_color=TEXT,
            font=heading_font(),
        ).pack(fill="x")
        fit_text(ctk.CTkLabel(
            middle, text=description, anchor="w", justify="left",
            text_color=MUTED, wraplength=780, font=body_font(),
        )).pack(fill="x", pady=(1, 0))
        # What this step's state actually is, filled in by refresh().
        state = fit_text(ctk.CTkLabel(
            middle, text="", anchor="w", justify="left", text_color=MUTED,
            wraplength=780, font=body_font(),
        ))
        state.pack(fill="x", pady=(5, 0))
        self._state_labels[key] = state

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="right", padx=16, pady=12)
        mark = ctk.CTkLabel(
            right, text="", text_color=MUTED, font=heading_font(18),
        )
        mark.pack(anchor="e", pady=(0, 2))
        self._marks[key] = mark
        button = ctk.CTkButton(
            right, text=action, width=170,
            command=lambda k=key: self._act(k),
        )
        button.pack(anchor="e", pady=(6, 0))
        self._buttons[key] = button

        if key == "model":
            # The one screen where "it does not work and I cannot tell you
            # why" is a real outcome. A packaged Windows build has no console,
            # so --model-check is unreachable there and the report has to be
            # obtainable from the window or not at all.
            ctk.CTkButton(
                right, text="Diagnosi", width=170, fg_color=BG_ROW,
                text_color=TEXT, command=self._diagnose,
            ).pack(anchor="e", pady=(6, 0))

    # ── acting ───────────────────────────────────────────────
    def _act(self, key: str) -> None:
        """Step 2 does its own work; the other two open the panel that does.

        The download is the one thing on this page with nowhere else to go —
        it belongs to no tab — so the path owns it and the Prediction panel's
        own strip picks up the result on the next refresh.
        """
        if key == "model":
            self.app.download_model(on_done=self.refresh)
            return
        self.app.show(key)

    def _diagnose(self) -> None:
        """Write the TimesFM report to a file and say where it is.

        A file rather than a dialog: it is forty lines, the useful thing to do
        with it is send it to somebody, and a message box is the one place
        text cannot be copied out of comfortably.
        """
        checkpoint = self._checkpoint()
        token = self.app.settings.get("hf_token", "")

        def work(report):
            from core.data_manager import DATA_DIR
            from core.model_store import diagnose

            report("interrogo pacchetti, cache e Hub…", 0.0)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            path = DATA_DIR / "diagnosi-timesfm.txt"
            path.write_text("\n".join(diagnose(checkpoint, token)), encoding="utf-8")
            return path

        self.app.run_worker(
            "Diagnosi TimesFM",
            work,
            lambda path: self.app.set_status(f"Diagnosi scritta in {path}"),
        )

    # ── state ────────────────────────────────────────────────
    def refresh(self) -> None:
        """Re-read every step. Called on each tab switch."""
        states = self._states()
        for key, (text, colour, mark) in states.items():
            self._state_labels[key].configure(text=text, text_color=colour)
            self._marks[key].configure(text=mark, text_color=colour)
        # Nothing to download when the weights are there, or when no download
        # would help — a missing package is not fixed by fetching a checkpoint.
        model = availability(self._checkpoint())
        self._buttons["model"].configure(
            state="normal" if model.can_download else "disabled",
            text="Scarica il modello" if model.can_download else "Niente da scaricare",
        )

    def _checkpoint(self) -> str:
        return self.app.settings.get("timesfm_checkpoint") or DEFAULT_TIMESFM_CHECKPOINT

    def _states(self) -> dict[str, tuple[str, str, str]]:
        """``{step: (state text, colour, mark)}``.

        One function returning plain data, so the smoke tests read the same
        answers the labels show rather than scraping widgets.
        """
        return {
            "archive": self._archive_state(),
            "model": self._model_state(),
            "prediction": self._prediction_state(),
        }

    def _archive_state(self) -> tuple[str, str, str]:
        draws = self.app.draws
        if not draws:
            return ("Nessun archivio. Aprilo e scaricalo: è una richiesta sola.",
                    WARN, "!")
        info = describe_archive(draws)
        summary = (
            f"{it_number(info['count'])} estrazioni, dal {it_date(info['first'])} "
            f"al {it_date(info['last'])}."
        )
        state = freshness(draws)
        if state.stale:
            return (
                f"{summary} Mancano circa {it_number(state.estimated_missing)} "
                "estrazioni: da aggiornare.",
                WARN, "!",
            )
        return (f"{summary} Aggiornato.", GOOD, "✓")

    def _model_state(self) -> tuple[str, str, str]:
        if self.app.forecaster is not None and self.app.forecaster.loaded:
            return ("TimesFM è caricato in memoria: le previsioni partono subito.",
                    GOOD, "✓")
        state = availability(self._checkpoint())
        if state.ready:
            return (state.detail, GOOD, "✓")
        return (state.detail, WARN, "!")

    def _prediction_state(self) -> tuple[str, str, str]:
        predictions = getattr(self.app, "last_predictions", None)
        if not self.app.draws:
            return ("Serve prima l'archivio.", MUTED, "·")
        if not predictions:
            return (
                "Non ancora generate. Qualunque metodo, il punteggio atteso è lo "
                "stesso: 0,4 numeri indovinati su sei.",
                MUTED, "·",
            )
        any_prediction = next(iter(predictions.values()))
        return (
            f"{it_count(len(predictions), 'metodo a confronto', 'metodi a confronto')}, "
            f"{it_count(len(any_prediction.combinations), 'combinazione', 'combinazioni')} "
            "ciascuno.",
            GOOD, "✓",
        )
