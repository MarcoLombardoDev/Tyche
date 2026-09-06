# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
app.py — Tyche

The main window: a top bar, five panels, and the worker-thread plumbing.

    ┌──────────────────────────────────────────────────────────────┐
    │ TYCHE   · status       [Percorso] [Prova] [Archivio] [Stats]  │
    │                        [Previsione] [Validazione] [⚙]         │
    │──────────────────────────────────────────────────────────────│
    │                                                              │
    │  the selected panel                                          │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘

**The path is the first tab.** Before 0.4.0 it was the reality check, on the
argument that a program opening on its caveats is more honest than one
opening on its output. The argument was right and the execution was not: six
independent tabs, each explaining itself and none explaining the order, and
the owner's verdict on the built application was that it was incomprehensible.

:mod:`gui.home_panel` replaces that with a route — archive, fairness,
validation, prediction — which reaches the combinations *through* the
evidence rather than instead of it. The reality check has not been demoted;
it is step 2 of 4 on the way to the thing the user came for, which is a
better place for it than a tab that can be skipped.

Threading follows the one rule Tk imposes: widgets are touched from the main
thread only. Workers put callables on a queue and :meth:`TycheApp._poll_queue`
runs them, so a background fetch never calls ``configure`` from off-thread —
which fails intermittently and only under load, i.e. in front of the user.
"""

from __future__ import annotations

import contextlib
import os
import queue
import threading
import traceback

import customtkinter as ctk

from core.archive import describe_archive, freshness, load_archive
from core.data_manager import ARCHIVE_PATH, load_settings, save_settings
from core.localise import it_date, it_number
from core.version import APP_NAME, APP_TITLE, __version__
from gui.archive_panel import ArchivePanel
from gui.home_panel import HomePanel
from gui.prediction_panel import PredictionPanel
from gui.reality_panel import RealityPanel
from gui.settings_panel import SettingsPanel
from gui.statistics_panel import StatisticsPanel
from gui.theme import ACCENT, BG_PANEL, BG_ROOT, MUTED, SEP, TEXT, WARN, apply_theme
from gui.validation_panel import ValidationPanel

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
apply_theme()

VIEWS = [
    ("home", "Percorso", HomePanel),
    ("reality", "Prova del nove", RealityPanel),
    ("archive", "Archivio", ArchivePanel),
    ("statistics", "Statistiche", StatisticsPanel),
    ("prediction", "Previsione", PredictionPanel),
    ("validation", "Validazione", ValidationPanel),
    ("settings", "Impostazioni", SettingsPanel),
]


class TycheApp(ctk.CTk):
    """Main window."""

    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.draws = load_archive(ARCHIVE_PATH)
        self.forecaster = None
        # What each step has produced this session. The path panel reads
        # these to say where the user is; nothing else depends on them, so
        # a panel that never runs simply leaves its entry None.
        self.last_reality = None
        self.last_validation = None
        self.last_prediction = None
        self._queue: queue.Queue = queue.Queue()
        self._panels: dict[str, ctk.CTkFrame] = {}
        self._active = "home"
        self._busy = False

        self.title(f"{APP_TITLE}  ·  v{__version__}")
        self.geometry("1280x840")
        self.minsize(1040, 680)
        self.configure(fg_color=BG_ROOT)

        self._build()
        self._set_window_icon()
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self) -> None:
        """Give the window the application icon.

        Two files, because Tk uses two: the PhotoImage works everywhere and Tk
        has read PNG since 8.6, and ``iconbitmap`` is tried afterwards on
        Windows for the sharper small sizes.

        The PhotoImage is kept on the instance. Tk holds only a weak reference
        to it, and a garbage-collected image leaves a blank icon.

        Never raises, and the two attempts are independent on purpose: one
        ``try`` around both would let a failing ``iconbitmap`` take the
        fallback down with it and leave Tk's default feather. A missing icon is
        cosmetic, and nothing cosmetic should stop the program starting.

        Same drawing as Argus, one letter apart — see tools/make_icon.py.
        """
        import tkinter as tk

        from core.paths import bundled_dir

        assets = bundled_dir() / "assets"

        png = assets / "app_icon.png"
        if png.exists():
            try:
                self._app_icon = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._app_icon)
            except Exception:  # noqa: BLE001 — see the docstring
                pass

        if os.name == "nt":
            ico = assets / "app_icon.ico"
            if ico.exists():
                with contextlib.suppress(Exception):
                    self.iconbitmap(str(ico))

    # ── layout ───────────────────────────────────────────────
    def _build(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=58)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar, text=APP_NAME.upper(), text_color=ACCENT,
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=(18, 6))
        ctk.CTkLabel(
            bar, text="Analisi dell'archivio SuperEnalotto", text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, 20))

        self._nav: dict[str, ctk.CTkButton] = {}
        for key, label, _ in VIEWS:
            button = ctk.CTkButton(
                bar, text=label, width=118, height=32, corner_radius=6,
                fg_color="transparent", text_color=TEXT, hover_color=SEP,
                command=lambda k=key: self.show(k),
            )
            button.pack(side="left", padx=3)
            self._nav[key] = button

        self.body = ctk.CTkFrame(self, fg_color=BG_ROOT)
        self.body.pack(fill="both", expand=True)

        footer = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=34)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self._status = ctk.CTkLabel(footer, text="", anchor="w", text_color=MUTED)
        self._status.pack(side="left", padx=16)
        self._archive_label = ctk.CTkLabel(footer, text="", anchor="e", text_color=MUTED)
        self._archive_label.pack(side="right", padx=16)

        for key, _, panel_class in VIEWS:
            self._panels[key] = panel_class(self.body, self)
        self.show(self._active)
        self._refresh_footer()
        if not self.draws:
            self.set_status(
                "Nessun archivio su disco — apri Archivio e scarica l'esportazione."
            )

    def show(self, key: str) -> None:
        for other in self._panels.values():
            other.pack_forget()
        for name, button in self._nav.items():
            button.configure(fg_color=ACCENT if name == key else "transparent")
        panel = self._panels[key]
        panel.pack(fill="both", expand=True)
        self._active = key
        with contextlib.suppress(Exception):
            panel.refresh()

    # ── shared state ─────────────────────────────────────────
    def set_draws(self, draws) -> None:
        self.draws = draws
        self._refresh_footer()
        with contextlib.suppress(Exception):
            self._panels[self._active].refresh()

    def set_status(self, message: str) -> None:
        self._status.configure(text=message)

    def save_settings(self) -> None:
        save_settings(self.settings)

    def _refresh_footer(self) -> None:
        """Draw count, span, and how far behind the archive is.

        The staleness marker is in the footer rather than only on the Archive
        tab because it qualifies every number the other five tabs show. A
        frequency table computed from an archive six years out of date is not
        wrong, but it is not about this year either.
        """
        info = describe_archive(self.draws)
        if not info["count"]:
            self._archive_label.configure(text="archivio vuoto", text_color=MUTED)
            return
        state = freshness(self.draws)
        suffix = (
            f"  ·  {it_number(state.estimated_missing)} estrazioni indietro"
            if state.stale else ""
        )
        self._archive_label.configure(
            text=(
                f"{it_number(info['count'])} estrazioni · "
                f"{it_date(info['first'])} → {it_date(info['last'])}{suffix}"
            ),
            text_color=WARN if state.stale else MUTED,
        )

    # ── worker threads ───────────────────────────────────────
    def run_worker(self, label: str, work, on_success) -> None:
        """Run ``work(report)`` off-thread and hand its result to ``on_success``.

        ``report(message, fraction)`` is passed into the worker and is safe to
        call from it: it only enqueues. One job at a time — two concurrent
        fetches would both write the archive, and the loser's draws would be
        silently dropped by whichever saved last.
        """
        if self._busy:
            self.set_status("C'è già un'operazione in corso — aspetta che finisca.")
            return
        self._busy = True
        self.set_status(f"{label}…")

        def report(message: str, fraction: float = 0.0) -> None:
            self._queue.put(lambda: self.set_status(f"{label}: {message}"))

        def run() -> None:
            try:
                result = work(report)
            except Exception as exc:
                # The message is formatted here, not in the lambda. Python
                # deletes the `except ... as exc` name when the block ends, so
                # a lambda that closes over `exc` raises NameError by the time
                # the main thread runs it — and the failure it was reporting
                # is replaced by a confusing one about a free variable.
                message = f"{label}: non riuscito — {exc}"
                print(f"[{label}] {traceback.format_exc(limit=3)}")
                self._queue.put(lambda m=message: self.set_status(m))
            else:
                self._queue.put(lambda: on_success(result))
            finally:
                self._queue.put(self._clear_busy)

        threading.Thread(target=run, daemon=True, name=label).start()

    def _clear_busy(self) -> None:
        self._busy = False

    def _poll_queue(self) -> None:
        while True:
            try:
                callback = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                traceback.print_exc()
        self.after(100, self._poll_queue)

    def _on_close(self) -> None:
        with contextlib.suppress(Exception):
            self.save_settings()
        self.destroy()
