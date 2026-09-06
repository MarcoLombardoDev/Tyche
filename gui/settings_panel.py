# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
settings_panel.py — Tyche

Edits ``config/settings.json``.

The fields are declared as data rather than laid out one by one, so adding a
setting to :data:`core.data_manager.DEFAULT_SETTINGS` and to this list is the
whole change. The Hugging Face token is the one field rendered masked; it is
a credential, ``config/settings.json`` is git-ignored, and the template that
is committed carries an empty string.
"""

from __future__ import annotations

import customtkinter as ctk

from core.fonts import ui_font_family
from core.version import DEFAULT_TIMESFM_CHECKPOINT
from gui.theme import BG_ROOT, MUTED
from gui.widgets import section

# (key, label, kind, help). kind is "text", "secret", "bool", or a tuple of
# choices. Every key in DEFAULT_SETTINGS that a user can meaningfully set
# belongs here; test_every_setting_is_read_somewhere catches the reverse
# mistake, a key nothing reads.
FIELDS = [
    ("timesfm_checkpoint", "Checkpoint TimesFM", "text",
     f"Identificativo del repository Hugging Face. Predefinito {DEFAULT_TIMESFM_CHECKPOINT}; "
     "i pesi della 3.0 sono per uso non commerciale e non di produzione."),
    ("timesfm_device", "Dispositivo", ("cpu", "cuda"),
     "cuda richiede una build di PyTorch corrispondente; cpu impiega qualche secondo "
     "per previsione."),
    ("hf_token", "Token Hugging Face", "secret",
     "Serve solo per un checkpoint ad accesso ristretto. Salvato in "
     "config/settings.json, che git ignora."),
    ("representation", "Serie data al modello", ("frequenza", "presenza", "ritardo"),
     "«frequenza» è lisciata e offre una pendenza da seguire; «presenza» è il dato "
     "grezzo 0/1 e produce una previsione piatta, cosa che vale la pena vedere una "
     "volta."),
    ("frequency_window", "Finestra mobile (estrazioni)", "text",
     "Finestra all'indietro per la serie di frequenza. 150 è circa un anno."),
    ("context_length", "Lunghezza del contesto (estrazioni)", "text",
     "Quanto storico vede TimesFM. La 3.0 accetta fino a 16k; 1024 tiene corta "
     "un'esecuzione su CPU."),
    ("bulk_archive_url", "Indirizzo del mirror storico", "text",
     "Una richiesta, tutto lo storico fino a gennaio 2020."),
    ("html_archive_url", "Indirizzo dell'archivio per anno", "text",
     "{year} viene sostituito. Modificabile perché la scansione non è mai stata "
     "provata sul sito reale e il percorso potrebbe essere sbagliato."),
    ("auto_repair_labels", "Correggi le etichette del mirror", "bool",
     "Il mirror storico etichetta 1998 le prime nove estrazioni del 1999. Con "
     "questa attiva vengono rimesse a posto durante l'import; disattivandola si "
     "importano i byte del mirror così come sono, che è il modo per confrontarli "
     "con un'altra fonte."),
    ("prediction_size", "Numeri per combinazione", tuple(str(n) for n in range(6, 13)),
     "Sei è una colonna singola. Di più è un sistema integrale: nove numeri "
     "coprono 84 colonne e costano 84 volte tanto. La probabilità sale nella "
     "stessa identica proporzione — un sistema è un modo di spendere di più, "
     "non di ottenere di più per euro. La scheda Previsione stampa le colonne."),
    ("predict_superstar", "Gioca anche il SuperStar", "bool",
     "Il SuperStar esce da un'urna separata, quindi è un numero da 1 a 90 "
     "indipendente dai sei e che può ripeterne uno. Indovinarlo è 1 su 90, "
     "sempre, e viene scelto sulla storia della sua urna e non su quella dei sei."),
    ("column_price", "Costo di una colonna (euro)", "text",
     "Quanto costa una singola colonna da sei numeri. Serve solo a calcolare "
     "il costo della giocata mostrata nella scheda Previsione: è un prezzo "
     "deciso dal concessionario, non dalla matematica, quindi si cambia qui."),
    ("superstar_price", "Costo del SuperStar (euro)", "text",
     "Si aggiunge per ogni colonna, non una volta sola: su un sistema il "
     "SuperStar costa quanto il sistema moltiplicato per questo prezzo."),
    ("validation_draws", "Estrazioni per la validazione", "text",
     "Quante estrazioni recenti valuta il backtest walk-forward."),
]


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._widgets: dict[str, ctk.CTkBaseClass] = {}
        self._build()

    def _build(self) -> None:
        block = section(
            self, "Impostazioni", "Salvate in config/settings.json."
        )
        block.pack(fill="both", expand=True, padx=16, pady=16)

        scroll = ctk.CTkScrollableFrame(block.body, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        for key, label, kind, helptext in FIELDS:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(row, text=label, width=200, anchor="w").pack(side="left")
            raw = self.app.settings.get(key, "")
            value = str(raw)
            if isinstance(kind, tuple):
                widget = ctk.CTkOptionMenu(row, width=260, values=list(kind))
                widget.set(value if value in kind else kind[0])
            elif kind == "bool":
                # get() returns 1 or 0, which _save reads through the same
                # "1"/"true"/"yes" rule every other boolean field would use.
                widget = ctk.CTkSwitch(row, text="")
                if bool(raw):
                    widget.select()
                else:
                    widget.deselect()
            else:
                widget = ctk.CTkEntry(row, width=440, show="•" if kind == "secret" else "")
                widget.insert(0, value)
            widget.pack(side="left")
            self._widgets[key] = widget
            ctk.CTkLabel(
                scroll, text=helptext, anchor="w", justify="left",
                text_color=MUTED, wraplength=900,
                font=ctk.CTkFont(family=ui_font_family(), size=11),
            ).pack(fill="x", padx=(200, 0), pady=(0, 10))

        ctk.CTkButton(block.body, text="Salva", width=120, command=self._save).pack(
            anchor="w", pady=(12, 0)
        )

    def _save(self) -> None:
        """Write the fields back, keeping the type each default declares.

        A setting whose default is an int stays an int. Without this every
        numeric field would come back from the entry box as a string, and the
        first ``int()`` downstream would be the one that raised.
        """
        from core.data_manager import DEFAULT_SETTINGS

        for key, widget in self._widgets.items():
            raw = widget.get()
            default = DEFAULT_SETTINGS.get(key)
            if isinstance(default, bool):
                value = str(raw).strip().lower() in ("1", "true", "yes")
            elif isinstance(default, int):
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    self.app.set_status(
                        f"{key}: «{raw}» non è un numero intero — non salvato."
                    )
                    return
            elif isinstance(default, float):
                # A comma is what an Italian keyboard produces for a price.
                try:
                    value = float(str(raw).strip().replace(",", "."))
                except (TypeError, ValueError):
                    self.app.set_status(
                        f"{key}: «{raw}» non è un numero — non salvato."
                    )
                    return
            else:
                value = raw
            self.app.settings[key] = value
        self.app.save_settings()
        # The forecaster caches the checkpoint, device and context it was
        # built with, so a saved change has to drop it or the next forecast
        # silently uses the old configuration.
        self.app.forecaster = None
        self.app.set_status(
            "Impostazioni salvate. TimesFM si ricaricherà alla prossima previsione."
        )

    def refresh(self) -> None:
        pass
