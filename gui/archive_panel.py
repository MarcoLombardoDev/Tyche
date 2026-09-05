# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
archive_panel.py — Tyche

Fetching, importing and inspecting the draw history.

The integrity report is given as much room as the draw list on purpose. The
archive this panel builds is wrong in a knowable way — the bulk mirror
mislabels nine draws and stops in 2020 — and a screen that shows three
thousand tidy rows without saying so invites the user to trust all of them
equally.
"""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from core.archive import (
    describe_archive,
    freshness,
    integrity_report,
    merge_draws,
    preview_merge,
    save_archive,
)
from core.data_manager import ARCHIVE_PATH, DATA_DIR
from core.localise import it_date, it_number
from core.sources import (
    BulkArchiveSource,
    EstrazioniItSource,
    HtmlTableSource,
    LocalFileSource,
)
from gui.theme import BG_ROOT, GOOD, MUTED, WARN
from gui.widgets import ReportBox, section


class ArchivePanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._build()

    def _build(self) -> None:
        sources = section(
            self, "Passo 1 di 4 · Porta i dati",
            "Senza archivio non c'è niente da analizzare. Il pulsante da premere la "
            "prima volta è «estrazioni.it»: una richiesta e l'archivio è completo.\n"
            "L'esportazione di estrazioni.it è la sorgente principale: una richiesta, "
            "dal 1997 all'ultima estrazione. Il mirror storico non richiede "
            "configurazione ma si ferma a gennaio 2020, e la scansione delle pagine "
            "non è mai stata provata su un sito reale. Prima di scrivere qualsiasi "
            "cosa viene sempre chiesta conferma.",
        )
        sources.pack(fill="x", padx=16, pady=(16, 8))
        row = ctk.CTkFrame(sources.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Aggiorna da estrazioni.it", width=210,
                      command=self._fetch_export).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Mirror storico (al 2020)", width=195,
                      command=self._fetch_bulk).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Scansiona le pagine", width=180,
                      command=self._fetch_html).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Importa un file…", width=155,
                      command=self._import_file).pack(side="left", padx=8)

        self.debug_html = ctk.CTkCheckBox(
            row, text="salva le pagine scaricate", width=200,
        )
        self.debug_html.pack(side="left", padx=(16, 0))

        self.status = ctk.CTkLabel(sources.body, text="", anchor="w", text_color=MUTED)
        self.status.pack(fill="x", pady=(10, 0))
        self.freshness = ctk.CTkLabel(
            sources.body, text="", anchor="w", justify="left", wraplength=1000
        )
        self.freshness.pack(fill="x", pady=(4, 0))

        health = section(
            self, "Integrità",
            "Che cosa non va nell'archivio su disco: date doppie, numeri di concorso "
            "ripetuti, buchi dentro un anno completo. Una lista vuota è il risultato "
            "buono. Fatto questo, vai al passo 2, Prova del nove.",
        )
        health.pack(fill="both", expand=True, padx=16, pady=8)
        self.health_box = ReportBox(health.body, height=150)
        self.health_box.pack(fill="both", expand=True)

        recent = section(self, "Estrazioni più recenti")
        recent.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.recent_box = ReportBox(recent.body, height=180)
        self.recent_box.pack(fill="both", expand=True)

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

    def _fetch_bulk(self) -> None:
        url = self.app.settings.get("bulk_archive_url", "")
        repair = bool(self.app.settings.get("auto_repair_labels", True))
        self.app.run_worker(
            "Bulk archive",
            lambda report: BulkArchiveSource(url, repair_labels=repair).fetch(report),
            self._merge_result,
        )

    def _fetch_html(self) -> None:
        """Scrape the years the archive does not already cover, plus the last one.

        Re-scraping the final year it already has is deliberate: that year is
        partial by definition, and the draws added since the last update are
        exactly the ones sitting in it.
        """
        template = self.app.settings.get("html_archive_url", "")
        last_year = self.app.draws[-1].year if self.app.draws else 1997
        years = list(range(last_year, date.today().year + 1))
        debug_dir = DATA_DIR / "fetched-pages" if self.debug_html.get() else None
        self.app.run_worker(
            f"Scraping {years[0]}–{years[-1]}",
            lambda report: HtmlTableSource(
                template, years, debug_dir=debug_dir
            ).fetch(report),
            # Always confirmed, even when the preview looks clean: this is the
            # source that has never been checked against a real page, and a
            # confident-looking mis-parse is exactly what it would produce.
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
        if not draws:
            self.status.configure(
                text="Ancora nessun archivio. Comincia da «Aggiorna da estrazioni.it»."
            )
            self.freshness.configure(text="", text_color=MUTED)
            self.health_box.set_text("")
            self.recent_box.set_text("")
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
