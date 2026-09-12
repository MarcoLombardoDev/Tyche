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

from core.version import DEFAULT_TIMESFM_CHECKPOINT
from gui.theme import BG_ROOT, BG_ROW, MUTED, TEXT
from gui.widgets import body_font, fit_text, section

# (key, label, kind, help). kind is "text", "secret", "folder", "bool", or a
# tuple of choices. Every key in DEFAULT_SETTINGS that a user can meaningfully set
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
     "Serve solo per un checkpoint ad accesso ristretto: quello predefinito "
     "non lo è, e senza token si scarica lo stesso. Se ti serve: huggingface.co "
     "→ crea un account → Settings → Access Tokens → New token, tipo «Read», e "
     "incolla qui la stringa che comincia con hf_. Salvato in "
     "config/settings.json, che git ignora."),
    ("timesfm_local_dir", "Cartella dei pesi TimesFM", "folder",
     "Da riempire solo se il download non riesce. Scarica a mano i due file "
     "config.json e model.safetensors dalla pagina huggingface.co/"
     f"{DEFAULT_TIMESFM_CHECKPOINT} (scheda «Files»), mettili in una cartella "
     "qualsiasi e incolla qui il suo percorso: Tyche carica da lì e non scarica "
     "più niente. Bastano quei due — gli altri file del repository non servono. "
     "Lascia vuoto per usare il download normale."),
    ("frequency_window", "Finestra mobile (estrazioni)", "text",
     "Quante estrazioni all'indietro guarda il metodo «frequenza» (e la serie "
     "lisciata, se è quella che dài al modello). 208 è un anno esatto alle "
     "quattro estrazioni a settimana di oggi: l'archivio ne conta 208 nel 2024 "
     "e 208 nel 2025. Fino al 2022 erano tre a settimana, cioè 156."),
    ("context_length", "Lunghezza del contesto (estrazioni)", "text",
     "Quanto storico vede TimesFM. La 3.0 accetta fino a 16k; 1024 tiene corta "
     "un'esecuzione su CPU."),
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
     "sempre, e viene scelto sulla storia della sua urna e non su quella dei "
     "sei — ogni metodo lo sceglie a modo suo. Con questa attiva la previsione "
     "di TimesFM costa il doppio: sono due passate del modello, una per urna."),
    ("column_price", "Costo di una colonna (euro)", "text",
     "Quanto costa una singola colonna da sei numeri. Serve solo a calcolare "
     "il costo della giocata mostrata nella scheda Previsione: è un prezzo "
     "deciso dal concessionario, non dalla matematica, quindi si cambia qui."),
    ("superstar_price", "Costo del SuperStar (euro)", "text",
     "Si aggiunge per ogni colonna, non una volta sola: su un sistema il "
     "SuperStar costa quanto il sistema moltiplicato per questo prezzo."),
]


# How far the field column, and therefore every help line, sits from the left.
HELP_INDENT = 200


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
            ctk.CTkLabel(
                row, text=label, width=HELP_INDENT, anchor="w", font=body_font(),
            ).pack(side="left")
            raw = self.app.settings.get(key, "")
            value = str(raw)
            extra = None
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
            elif kind == "folder":
                # Typed by hand this is a Windows path with backslashes in it,
                # copied out of an address bar by somebody who has just spent
                # an hour fighting a download. The picker is the difference
                # between "it does not work" and a path with one character
                # wrong. The entry stays the widget _save() reads, so the
                # field is still editable and still a plain string.
                widget = ctk.CTkEntry(row, width=340)
                widget.insert(0, value)
                extra = ctk.CTkButton(
                    row, text="Sfoglia…", width=94, fg_color=BG_ROW,
                    text_color=TEXT, command=lambda w=widget: self._choose(w),
                )
            else:
                widget = ctk.CTkEntry(row, width=440, show="•" if kind == "secret" else "")
                widget.insert(0, value)
            # One pack for every kind. Packing inside the branches instead cost
            # three option menus and two switches, which came up 1x1 and
            # unmapped — a branch that forgets it is invisible rather than
            # wrong, and the screenshot is what showed it.
            widget.pack(side="left")
            if extra is not None:
                extra.pack(side="left", padx=(6, 0))
            self._widgets[key] = widget
            # The margin has to carry the indent. fit_text measures the
            # parent, and this label starts 200px into it — with the default
            # margin every help line wrapped 200px too late and ran off the
            # right edge of the box. Visible on the screenshot, invisible to
            # every test, and worst on the longest line, which is the one
            # explaining what to do when the download will not finish.
            fit_text(ctk.CTkLabel(
                scroll, text=helptext, anchor="w", justify="left",
                text_color=MUTED, font=body_font(),
            ), margin=HELP_INDENT + 32).pack(fill="x", padx=(HELP_INDENT, 0), pady=(0, 10))

        ctk.CTkButton(block.body, text="Salva", width=120, command=self._save).pack(
            anchor="w", pady=(12, 0)
        )

    def _choose(self, entry) -> None:
        """Pick a folder and put it in the field.

        Cancelling returns an empty string, which must leave what is there
        alone: a picker that empties the field on Escape would throw away a
        path the user had already typed.
        """
        from tkinter import filedialog

        chosen = filedialog.askdirectory(
            title="La cartella con config.json e model.safetensors",
            initialdir=entry.get() or None,
        )
        if not chosen:
            return
        entry.delete(0, "end")
        entry.insert(0, chosen)

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
