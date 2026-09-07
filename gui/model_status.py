# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
model_status.py — Tyche

The strip that says whether TimesFM can run, and offers the download if not.

One widget, used by both panels that can start a forecast. Two copies of this
would be two places for the rule "do not offer a method that cannot run" to be
stated, and the second copy is the one that gets forgotten — which is exactly
how the defect this fixes arrived: the Prediction panel and the Validation
panel each built their own TimesFM branch, and both of them reported a missing
checkpoint as a failed run.

The state is read before the user can act on it, never as the result of
acting. :func:`core.model_store.availability` imports nothing heavy, so
:meth:`ModelStatus.refresh` is cheap enough to run on every tab switch — and
tab switch is when it has to run, because the download that made TimesFM
available may have happened on the other tab.
"""

from __future__ import annotations

import customtkinter as ctk

from core.model_store import availability, download_checkpoint
from core.version import DEFAULT_TIMESFM_CHECKPOINT
from gui.theme import GOOD, MUTED, WARN


class ModelStatus(ctk.CTkFrame):
    """Reports TimesFM's availability and downloads the weights on request.

    ``on_change(available)`` is called after every refresh, with the panel's
    own enabling and disabling as the intended body: this widget knows whether
    the method can run, and the panel knows what to grey out.
    """

    def __init__(self, parent, app, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._on_change = on_change
        self._state = None

        self.label = ctk.CTkLabel(
            self, text="", anchor="w", justify="left",
            text_color=MUTED, wraplength=760,
        )
        self.label.pack(side="left")

        # Built once and packed or forgotten, rather than created per refresh:
        # a widget rebuilt on every tab switch is a widget whose command can
        # fire after it has been destroyed.
        self.button = ctk.CTkButton(
            self, text="Scarica il modello", width=170, command=self._download,
        )

    # ── state ────────────────────────────────────────────────
    def _checkpoint(self) -> str:
        return (
            self.app.settings.get("timesfm_checkpoint")
            or DEFAULT_TIMESFM_CHECKPOINT
        )

    def refresh(self) -> None:
        """Re-read the state and redraw. Safe to call as often as you like."""
        if self.app.forecaster is not None and self.app.forecaster.loaded:
            # Loaded this session: the cache query would say the same thing
            # and cost a filesystem walk to say it.
            self._apply(
                "TimesFM è caricato in memoria: le previsioni partono subito.",
                GOOD, can_download=False, available=True,
            )
            return
        state = availability(self._checkpoint())
        self._apply(
            state.detail,
            GOOD if state.ready else WARN,
            can_download=state.can_download,
            available=state.usable,
        )

    def _apply(self, text: str, colour: str, can_download: bool, available: bool) -> None:
        self.label.configure(text=text, text_color=colour)
        if can_download:
            self.button.pack(side="left", padx=(14, 0))
        else:
            self.button.pack_forget()
        self._state = available
        if self._on_change is not None:
            self._on_change(available)

    @property
    def available(self) -> bool:
        return bool(self._state)

    # ── the download ─────────────────────────────────────────
    def _download(self) -> None:
        checkpoint = self._checkpoint()
        token = self.app.settings.get("hf_token", "")

        def work(report):
            return download_checkpoint(checkpoint, token=token, progress=report)

        self.app.run_worker("TimesFM", work, self._downloaded)

    def _downloaded(self, path: str) -> None:
        self.refresh()
        self.app.set_status(f"Pesi di {self._checkpoint()} scaricati in {path}.")
