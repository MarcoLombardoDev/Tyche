# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
app.py — Tyche

The main window: a top bar, four panels, and the worker-thread plumbing.

    ┌──────────────────────────────────────────────────────────────┐
    │ TYCHE   · status   [Percorso] [Archivio] [Previsione]         │
    │                    [Impostazioni]                             │
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

:mod:`gui.home_panel` replaces that with a route — archive, model,
prediction — the three conditions that have to hold before a forecast can
run. The evidence tabs it used to pass through were removed in 0.10.0 on the
owner's instruction; what carries their argument now is the Prediction panel
running all four methods at once, with the random control beside TimesFM at
the same size.

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
import webbrowser
from urllib.parse import quote

import customtkinter as ctk

from core.archive import describe_archive, freshness, load_archive
from core.data_manager import ARCHIVE_PATH, load_settings, save_settings
from core.fonts import ui_font_family
from core.localise import it_date, it_number
from core.model_store import download_checkpoint
from core.version import (
    APP_NAME,
    APP_TITLE,
    CONTACT_EMAIL,
    DEFAULT_TIMESFM_CHECKPOINT,
    __version__,
)
from gui.archive_panel import ArchivePanel
from gui.home_panel import HomePanel
from gui.prediction_panel import PredictionPanel
from gui.settings_panel import SettingsPanel
from gui.theme import ACCENT, BG_PANEL, BG_ROOT, MUTED, SEP, TEXT, WARN, apply_theme

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
apply_theme()

VIEWS = [
    ("home", "Percorso", HomePanel),
    ("archive", "Archivio", ArchivePanel),
    ("prediction", "Previsione", PredictionPanel),
    ("settings", "Impostazioni", SettingsPanel),
]


class TycheApp(ctk.CTk):
    """Main window."""

    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.draws = load_archive(ARCHIVE_PATH)
        self.forecaster = None
        # What the prediction panel last produced, as {method: Prediction}.
        # The path panel reads it to say where the user is; nothing else
        # depends on it, so a session that never generates leaves it None.
        self.last_predictions = None
        self._queue: queue.Queue = queue.Queue()
        self._panels: dict[str, ctk.CTkFrame] = {}
        self._active = "home"
        self._busy = False

        self.title(f"{APP_TITLE}  ·  v{__version__}")
        # The size the window falls back to: what it gets if maximising is
        # refused, and what it returns to when the user un-maximises it.
        self.geometry("1280x840")
        self.minsize(1040, 680)
        self.configure(fg_color=BG_ROOT)

        self._build()
        self._set_window_icon()
        # After the first idle pass, not here: on X11 the window has no real
        # size until it has been mapped, so a maximise attempted now measures
        # 1x1 and concludes it failed. Every product in this family does it
        # the same way and for the same reason.
        self.after(250, self._maximize)
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _maximize(self) -> None:
        """Maximises the window in a cross-platform way.

        Each attempt is measured rather than trusted. Argus's first version
        stopped at the first call that did not raise, and not raising is not
        the same as having worked: with no window manager running, both of the
        first two are accepted in silence and change nothing, and the chain
        then never reaches the one that would have worked.
        """
        def filled() -> bool:
            try:
                self.update_idletasks()
                return (
                    self.winfo_width() >= self.winfo_screenwidth() * 0.9
                    and self.winfo_height() >= self.winfo_screenheight() * 0.8
                )
            except Exception:  # noqa: BLE001 — a wrong size must not stop start-up
                return False

        with contextlib.suppress(Exception):
            self.update_idletasks()

        for attempt in (
            lambda: self.state("zoomed"),
            lambda: self.attributes("-zoomed", True),
            lambda: self.geometry(
                f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0"
            ),
        ):
            try:
                attempt()
            except Exception:  # noqa: BLE001
                continue
            if filled():
                return

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
            font=ctk.CTkFont(family=ui_font_family(), size=20, weight="bold"),
        ).pack(side="left", padx=(18, 6))
        ctk.CTkLabel(
            # The payoff from APP_TITLE, which the window title already
            # carries whole. Sliced rather than repeated so the two cannot
            # drift apart.
            bar, text=APP_TITLE.split(" — ", 1)[-1], text_color=MUTED,
            font=ctk.CTkFont(family=ui_font_family(), size=12),
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

        # The licence bar and the status footer are built and packed BEFORE the
        # body, and both to the bottom. `pack` hands the expanding widget
        # whatever is left and simply clips anything packed after it, so with
        # the body first these two vanished on exactly the tabs whose content
        # is tallest — Archivio and Previsione — which is where a user is most
        # likely to want to read the status line. Packed first they reserve
        # their height and are on every tab.
        self._build_licence_bar()

        footer = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=34)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self._status = ctk.CTkLabel(footer, text="", anchor="w", text_color=MUTED)
        self._status.pack(side="left", padx=16)
        self._archive_label = ctk.CTkLabel(footer, text="", anchor="e", text_color=MUTED)
        self._archive_label.pack(side="right", padx=16)

        self.body = ctk.CTkFrame(self, fg_color=BG_ROOT)
        self.body.pack(fill="both", expand=True)

        for key, _, panel_class in VIEWS:
            self._panels[key] = panel_class(self.body, self)
        self.show(self._active)
        self._refresh_footer()
        if not self.draws:
            self.set_status(
                "Nessun archivio su disco — apri Archivio e scarica l'esportazione."
            )

    # ── the licence bar ──────────────────────────────────────
    def _build_licence_bar(self) -> None:
        """A fixed strip naming the licence and how to ask about it.

        The same strip every product in this family carries, in the same place
        and saying the same things — but **in Italian**, unlike theirs. Tyche
        forecasts an Italian lottery and exists only for people who play it, so
        the language boundary in CLAUDE.md applies here like anywhere else a
        user reads something. ``AGPL-3.0`` is left alone: it is an SPDX
        identifier, not a phrase.

        Packed first of the three and to the bottom, so it sits below the
        status footer: with ``side="bottom"`` Tk stacks each new widget above
        the last. Both go in before the body, which expands — otherwise pack
        gives the body everything and clips these two off the window.

        Whoever is running the program is exactly the person who might have a
        question about licensing, security or contributing, so the address is
        written out and clickable rather than promised on request.
        """
        bar = ctk.CTkFrame(self, fg_color=BG_ROOT, corner_radius=0, height=24)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        # A transparent frame with no fill stays centred in the bar.
        centre = ctk.CTkFrame(bar, fg_color="transparent")
        centre.pack(expand=True)

        # Both kept on the instance so the suite can read them back rather
        # than walking the widget tree looking for a © sign.
        self._licence_label = ctk.CTkLabel(
            centre,
            text=(
                f"© 2026 Marco Lombardo — {APP_NAME}  |  "
                "Distribuito con licenza AGPL-3.0  |  Contatti:"
            ),
            font=ctk.CTkFont(family=ui_font_family(), size=11),
            # MUTED, not SEP: SEP is the colour of a hairline rule and the
            # strip was effectively invisible against the background.
            text_color=MUTED,
        )
        self._licence_label.pack(side="left")

        self._licence_email = ctk.CTkLabel(
            centre,
            text=CONTACT_EMAIL,
            font=ctk.CTkFont(family=ui_font_family(), size=11, underline=True),
            text_color=ACCENT,
            cursor="hand2",
        )
        self._licence_email.pack(side="left", padx=(4, 0))
        self._licence_email.bind("<Button-1>", self.open_contact_email)

    def open_contact_email(self, event=None) -> None:
        """Open the mail client on a contact enquiry.

        The subject is Italian like the rest of what a user sees; the docstring
        is English like the rest of what a developer sees.

        Suppressed rather than reported: with no mail client configured the
        address is still legible on screen, so there is nothing a dialog would
        tell the reader that they cannot already see.
        """
        subject = quote(f"{APP_TITLE} — richiesta")
        with contextlib.suppress(Exception):
            webbrowser.open(f"mailto:{CONTACT_EMAIL}?subject={subject}")

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

    def download_model(self, on_done=None) -> None:
        """Fetch the TimesFM weights, reporting the percentage in the footer.

        Here rather than in a panel because two of them offer the download —
        the path's step 2 and the strip on the Prediction tab — and two copies
        would be two places for "which checkpoint, with which token" to be
        decided. The worker reports through :meth:`run_worker`, so the
        percentage lands in the status bar like every other long job.
        """
        checkpoint = (
            self.settings.get("timesfm_checkpoint") or DEFAULT_TIMESFM_CHECKPOINT
        )
        token = self.settings.get("hf_token", "")

        def work(report):
            return download_checkpoint(checkpoint, token=token, progress=report)

        def done(path):
            self.set_status(f"Pesi di {checkpoint} scaricati in {path}.")
            if on_done is not None:
                on_done()
            with contextlib.suppress(Exception):
                self._panels[self._active].refresh()

        self.run_worker("TimesFM", work, done)

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
