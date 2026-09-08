# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
model_status.py — Tyche

The strip that says whether TimesFM can run, and offers the download if not.

The state is read before the user can act on it, never as the result of
acting — which is the defect this replaces. The Prediction panel used to build
a forecaster, import timesfm, let Hugging Face download or fail, and turn the
exception into a sentence, so "the weights are not here yet" arrived as a
failed run. :func:`core.model_store.availability` imports nothing heavy, so
:meth:`refresh` is cheap enough to call on every tab switch — and tab switch
is when it has to run, because the download may have been started from the
path panel's step 2.
"""

from __future__ import annotations

import customtkinter as ctk

from core.model_store import availability
from core.version import DEFAULT_TIMESFM_CHECKPOINT
from gui.theme import GOOD, MUTED, WARN
from gui.widgets import fit_text


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

        self.label = fit_text(ctk.CTkLabel(
            self, text="", anchor="w", justify="left",
            text_color=MUTED, wraplength=760,
        ))
        self.label.pack(side="left", fill="x", expand=True)

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
        """Hand off to the app, which owns the one implementation.

        The path panel's step 2 offers the same download, and two copies would
        be two places deciding which checkpoint and which token to use.
        """
        self.app.download_model(on_done=self.refresh)
