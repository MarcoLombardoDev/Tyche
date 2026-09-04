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

from core.archive import describe_archive, integrity_report, merge_draws, save_archive
from core.data_manager import ARCHIVE_PATH
from core.sources import BulkArchiveSource, HtmlTableSource, LocalFileSource
from gui.theme import BG_ROOT, MUTED
from gui.widgets import ReportBox, section


class ArchivePanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._build()

    def _build(self) -> None:
        sources = section(
            self, "Sources",
            "Bootstrap the history in one request, then keep it current. "
            "The bulk mirror covers 1997 to January 2020 and is no longer updated; "
            "the scraper has never been run against the live site, so check what it imports.",
        )
        sources.pack(fill="x", padx=16, pady=(16, 8))
        row = ctk.CTkFrame(sources.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Bootstrap from bulk archive", width=210,
                      command=self._fetch_bulk).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Scrape recent years", width=170,
                      command=self._fetch_html).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Import a file…", width=140,
                      command=self._import_file).pack(side="left", padx=8)

        self.status = ctk.CTkLabel(sources.body, text="", anchor="w", text_color=MUTED)
        self.status.pack(fill="x", pady=(10, 0))

        health = section(self, "Integrity", "What is wrong with the archive on disk.")
        health.pack(fill="both", expand=True, padx=16, pady=8)
        self.health_box = ReportBox(health.body, height=150)
        self.health_box.pack(fill="both", expand=True)

        recent = section(self, "Most recent draws")
        recent.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.recent_box = ReportBox(recent.body, height=180)
        self.recent_box.pack(fill="both", expand=True)

    # ── actions ──────────────────────────────────────────────
    def _fetch_bulk(self) -> None:
        url = self.app.settings.get("bulk_archive_url", "")
        self.app.run_worker(
            "Bulk archive",
            lambda report: BulkArchiveSource(url).fetch(report),
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
        self.app.run_worker(
            f"Scraping {years[0]}–{years[-1]}",
            lambda report: HtmlTableSource(template, years).fetch(report),
            self._merge_result,
        )

    def _import_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Import a SuperEnalotto archive",
            filetypes=[("Archive files", "*.csv *.txt *.tsv"), ("All files", "*.*")],
        )
        if not path:
            return
        self.app.run_worker(
            f"Importing {path}",
            lambda report: LocalFileSource(path).fetch(report),
            self._merge_result,
        )

    def _merge_result(self, incoming) -> None:
        merged, added, updated = merge_draws(self.app.draws, incoming)
        save_archive(ARCHIVE_PATH, merged)
        self.app.set_draws(merged)
        self.app.set_status(
            f"{added} draws added, {updated} updated — {len(merged):,} on record."
        )

    # ── display ──────────────────────────────────────────────
    def refresh(self) -> None:
        draws = self.app.draws
        info = describe_archive(draws)
        if not draws:
            self.status.configure(text="No archive yet. Start with the bulk bootstrap.")
            self.health_box.set_text("")
            self.recent_box.set_text("")
            return
        self.status.configure(
            text=(
                f"{info['count']:,} draws, {info['first']} to {info['last']}, "
                f"{info['with_superstar']:,} with a SuperStar. Stored in {ARCHIVE_PATH}."
            )
        )

        issues = integrity_report(draws)
        if not issues:
            self.health_box.set_text(
                "No internal inconsistencies.\n\n"
                "That means the archive agrees with itself — no duplicated dates, no\n"
                "duplicated contest numbers, no missing contests inside a complete year.\n"
                "It does not mean the numbers are right; only a second source can say that."
            )
        else:
            errors = sum(1 for i in issues if i.severity == "error")
            lines = [
                f"{len(issues)} issues — {errors} errors, {len(issues) - errors} warnings.",
                "",
            ]
            lines += [f"[{i.severity:<7}] {i.message}" for i in issues]
            self.health_box.set_text("\n".join(lines))

        header = (
            f"{'date':<12} {'contest':>8}  numbers                      "
            f"{'J':>3} {'SS':>3}  source"
        )
        lines = [header, "─" * len(header)]
        for d in draws[-25:][::-1]:
            nums = " ".join(f"{n:2d}" for n in d.numbers)
            lines.append(
                f"{d.date.isoformat():<12} {d.draw_id:>8}  {nums}   "
                f"{d.jolly or 0:>3} {d.superstar or 0:>3}  {d.source}"
            )
        self.recent_box.set_text("\n".join(lines))
