# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
archive_panel.py — Tyche

Fetching, importing and inspecting the draw history — and, since 0.11.0, the
archive in figures, which used to be a tab of its own.

Two columns. On the left what is *wrong* with the archive and what came in
last; on the right what is *in* it, number by number. They belong on one
screen because they are halves of the same question, and the Statistics tab
was a place a reader went once and never again.

The integrity report is given as much room as the draw list on purpose. The
archive this panel builds is wrong in a knowable way — the bulk mirror
mislabels nine draws and stops in 2020 — and a screen that shows three
thousand tidy rows without saying so invites the user to trust all of them
equally.

**Two source buttons went in 0.11.0** and the reasoning is worth keeping. The
bulk mirror stops at January 2020 and disagrees with estrazioni.it about
twelve draws; the page scraper has never once parsed a live page and its URLs
were guesses. Both sat on screen beside a button that fetches the whole
archive correctly in one request, which made them traps rather than options.
They survive as fallbacks inside ``--update``, where nobody has to choose
between them, and their two URL settings went with the buttons.
"""

from __future__ import annotations

import customtkinter as ctk

from core.archive import (
    describe_archive,
    freshness,
    integrity_report,
    merge_draws,
    preview_merge,
    save_archive,
)
from core.data_manager import ARCHIVE_PATH
from core.localise import it_date, it_number
from core.sources import EstrazioniItSource, LocalFileSource
from core.statistics import decade_report, number_report, pairs_report, summary_lines
from gui.theme import BG_ROOT, GOOD, MUTED, WARN
from gui.widgets import ReportBox, body_font, fit_text, section


class ArchivePanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._build()

    def _build(self) -> None:
        sources = section(
            self, "L'archivio",
            "Lo storico completo in una richiesta, dal 3 dicembre 1997 all'ultima "
            "estrazione. Premi «Aggiorna da estrazioni.it»: prima di scrivere "
            "qualsiasi cosa viene sempre chiesta conferma, con l'elenco di che cosa "
            "cambierebbe.",
        )
        sources.pack(fill="x", padx=16, pady=(16, 8))
        row = ctk.CTkFrame(sources.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Aggiorna da estrazioni.it", width=210,
                      command=self._fetch_export).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Importa un file…", width=155,
                      command=self._import_file).pack(side="left", padx=8)

        self.status = ctk.CTkLabel(
            sources.body, text="", anchor="w", text_color=MUTED, font=body_font(),
        )
        self.status.pack(fill="x", pady=(10, 0))
        self.freshness = fit_text(ctk.CTkLabel(
            sources.body, text="", anchor="w", justify="left", wraplength=1000,
            font=body_font(),
        ))
        self.freshness.pack(fill="x", pady=(4, 0))

        # Two equal columns: what is wrong with the archive, and what is in it.
        columns = ctk.CTkFrame(self, fg_color=BG_ROOT)
        columns.pack(fill="both", expand=True)
        columns.grid_columnconfigure(0, weight=1, uniform="half")
        columns.grid_columnconfigure(1, weight=1, uniform="half")
        columns.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(columns, fg_color=BG_ROOT)
        left.grid(row=0, column=0, sticky="nsew")
        right = ctk.CTkFrame(columns, fg_color=BG_ROOT)
        right.grid(row=0, column=1, sticky="nsew")

        health = section(
            left, "Integrità",
            "Date doppie, numeri di concorso ripetuti, buchi dentro un anno "
            "completo. Una lista vuota è il risultato buono.",
        )
        health.pack(fill="both", expand=True, padx=(16, 8), pady=(0, 8))
        self.health_box = ReportBox(health.body, height=120)
        self.health_box.pack(fill="both", expand=True)

        recent = section(left, "Estrazioni più recenti")
        recent.pack(fill="both", expand=True, padx=(16, 8), pady=(0, 16))
        self.recent_box = ReportBox(recent.body, height=140)
        self.recent_box.pack(fill="both", expand=True)

        figures = section(
            right, "L'archivio in cifre",
            "Niente qui aiuta a prevedere: serve a vedere che cosa produce davvero "
            "un gioco equo, che è raramente quello che ci si aspetta.",
        )
        figures.pack(fill="x", padx=(8, 16), pady=(0, 8))
        self.summary = fit_text(ctk.CTkLabel(
            figures.body, text="", anchor="w", justify="left", text_color=MUTED,
            font=body_font(),
        ))
        self.summary.pack(fill="x")

        self.tabs = ctk.CTkTabview(right, fg_color=BG_ROOT)
        self.tabs.pack(fill="both", expand=True, padx=(8, 16), pady=(0, 16))
        for name in ("Frequenze e ritardi", "Decine", "Coppie"):
            self.tabs.add(name)
        self.freq_box = ReportBox(self.tabs.tab("Frequenze e ritardi"), height=200)
        self.freq_box.pack(fill="both", expand=True)
        self.decade_box = ReportBox(self.tabs.tab("Decine"), height=200)
        self.decade_box.pack(fill="both", expand=True)
        self.pairs_box = ReportBox(self.tabs.tab("Coppie"), height=200)
        self.pairs_box.pack(fill="both", expand=True)

    # ── actions ──────────────────────────────────────────────
    def _fetch_export(self) -> None:
        """The whole archive in one request, always confirmed before writing.

        Confirmed even when the preview is clean, for the same reason the
        scraper is: the download URL was inferred from two other URLs on the
        site rather than read from any documentation, so a day when it starts
        returning something else is a day the user should see what arrived.
        """
        self.app.run_worker(
            "estrazioni.it export",
            lambda report: EstrazioniItSource().fetch(report),
            lambda incoming: self._merge_result(incoming, always_confirm=True),
        )

    def _import_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Importa un archivio SuperEnalotto",
            filetypes=[("File di archivio", "*.csv *.txt *.tsv"), ("Tutti i file", "*.*")],
        )
        if not path:
            return
        self.app.run_worker(
            f"Importing {path}",
            lambda report: LocalFileSource(path).fetch(report),
            self._merge_result,
        )

    def _merge_result(self, incoming, always_confirm: bool = False) -> None:
        """Show what the fetch would do, then write it — or not.

        The archive has no undo and the parsers are of uneven reliability, so
        a merge that would contradict stored draws or introduce integrity
        errors is put to the user rather than performed. A clean merge from a
        trusted source goes straight through: a confirmation dialog that
        always says "everything is fine" is one nobody reads.
        """
        preview = preview_merge(self.app.draws, incoming)
        if (always_confirm and (preview.added or preview.updated)) or not preview.safe:
            from tkinter import messagebox

            if not messagebox.askyesno("Conferma l'import", self._confirm_text(preview)):
                self.app.set_status("Import annullato — non è stato scritto nulla.")
                return

        merged, added, updated = merge_draws(self.app.draws, incoming)
        save_archive(ARCHIVE_PATH, merged)
        self.app.set_draws(merged)
        self.app.set_status(
            f"{added} estrazioni aggiunte, {updated} aggiornate — "
            f"{it_number(len(merged))} in archivio."
        )

    @staticmethod
    def _confirm_text(preview) -> str:
        lines = [preview.describe(), ""]
        if preview.samples:
            lines.append("Le righe più recenti che verrebbero aggiunte:")
            lines += [
                f"  {d.date}  {' '.join(f'{n:2d}' for n in d.numbers)}   [{d.source}]"
                for d in preview.samples
            ]
            lines.append("")
        lines.append("Le scrivo nell'archivio?")
        return "\n".join(lines)

    # ── display ──────────────────────────────────────────────
    def refresh(self) -> None:
        draws = self.app.draws
        info = describe_archive(draws)
        self.summary.configure(text="\n".join(summary_lines(draws)))
        if not draws:
            self.status.configure(
                text="Ancora nessun archivio. Comincia da «Aggiorna da estrazioni.it»."
            )
            self.freshness.configure(text="", text_color=MUTED)
            for box in (self.health_box, self.recent_box,
                        self.freq_box, self.decade_box, self.pairs_box):
                box.set_text("")
            return
        self.status.configure(
            text=(
                f"{it_number(info['count'])} estrazioni, dal {it_date(info['first'])} "
                f"al {it_date(info['last'])}, {it_number(info['with_superstar'])} con "
                f"SuperStar. Archivio in {ARCHIVE_PATH}."
            )
        )
        state = freshness(draws)
        self.freshness.configure(
            text=state.describe(), text_color=WARN if state.stale else GOOD
        )

        issues = integrity_report(draws)
        if not issues:
            self.health_box.set_text(
                "Nessuna incoerenza interna.\n\n"
                "Vuol dire che l'archivio è coerente con sé stesso: nessuna data\n"
                "duplicata, nessun numero di concorso duplicato, nessun concorso\n"
                "mancante dentro un anno completo.\n"
                "Non vuol dire che i numeri siano giusti: quello lo può dire solo\n"
                "una seconda fonte."
            )
        else:
            errors = sum(1 for i in issues if i.severity == "error")
            lines = [
                f"{len(issues)} problemi — {errors} errori, "
                f"{len(issues) - errors} avvisi.",
                "",
            ]
            lines += [f"[{i.severity:<7}] {i.message}" for i in issues]
            self.health_box.set_text("\n".join(lines))

        header = (
            f"{'data':<12} {'concorso':>9}  numeri                       "
            f"{'J':>3} {'SS':>3}  sorgente"
        )
        lines = [header, "─" * len(header)]
        for d in draws[-25:][::-1]:
            nums = " ".join(f"{n:2d}" for n in d.numbers)
            lines.append(
                f"{it_date(d.date):<12} {d.draw_id:>9}  {nums}   "
                f"{d.jolly or 0:>3} {d.superstar or 0:>3}  {d.source}"
            )
        self.recent_box.set_text("\n".join(lines))

        self.freq_box.set_text(number_report(draws))
        self.decade_box.set_text(decade_report(draws))
        self.pairs_box.set_text(pairs_report(draws))
