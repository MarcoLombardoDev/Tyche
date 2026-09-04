# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
prediction_panel.py — Tyche

Generates combinations and shows what they are worth.

The method selector offers ``random`` alongside TimesFM, at the same size, in
the same list. That is the design: a user who can pick the control condition
from the same menu, and watch it produce equally confident-looking balls, has
been told something no warning banner conveys.
"""

from __future__ import annotations

import customtkinter as ctk

from core.data_manager import log_prediction
from core.features import DEFAULT_WINDOW
from core.forecaster import TimesFMForecaster
from core.predictor import METHODS, predict, value_note
from gui.theme import BG_ROOT, MUTED
from gui.widgets import ReportBox, ball_row, section

_METHOD_LABELS = {
    "timesfm": "TimesFM 3.0 (330M foundation model)",
    "frequency": "Hot numbers (most drawn recently)",
    "gap": "Ritardo (absent longest)",
    "random": "Random (the control condition)",
}


class PredictionPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._prediction = None
        self._build()

    def _build(self) -> None:
        controls = section(
            self, "Generate combinations",
            "Every method below has the same expected score: 0.4 of the six numbers. "
            "The Validation tab measures it.",
        )
        controls.pack(fill="x", padx=16, pady=(16, 8))
        row = ctk.CTkFrame(controls.body, fg_color="transparent")
        row.pack(fill="x")

        ctk.CTkLabel(row, text="Method", text_color=MUTED).pack(side="left", padx=(0, 6))
        self.method = ctk.CTkOptionMenu(
            row, width=300, values=[_METHOD_LABELS[m] for m in METHODS]
        )
        self.method.set(_METHOD_LABELS[self.app.settings.get("prediction_method", "frequency")])
        self.method.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row, text="Combinations", text_color=MUTED).pack(side="left", padx=(0, 6))
        self.count = ctk.CTkOptionMenu(row, width=70, values=[str(i) for i in range(1, 11)])
        self.count.set(str(self.app.settings.get("combinations", 5)))
        self.count.pack(side="left", padx=(0, 16))

        ctk.CTkButton(row, text="Generate", width=120, command=self._generate).pack(side="left")

        self.note = ctk.CTkLabel(
            controls.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=1000
        )
        self.note.pack(fill="x", pady=(10, 0))

        self.output = section(self, "Combinations")
        self.output.pack(fill="x", padx=16, pady=8)
        self.balls = ctk.CTkFrame(self.output.body, fg_color="transparent")
        self.balls.pack(fill="x")

        detail = section(self, "Scores and odds")
        detail.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.box = ReportBox(detail.body, height=240)
        self.box.pack(fill="both", expand=True)
        self.box.set_text(value_note())

    def _selected_method(self) -> str:
        label = self.method.get()
        for key, text in _METHOD_LABELS.items():
            if text == label:
                return key
        return "frequency"

    def _generate(self) -> None:
        draws = self.app.draws
        if not draws:
            self.app.set_status("No archive yet — fetch one from the Archive tab.")
            return
        method = self._selected_method()
        count = int(self.count.get())
        settings = self.app.settings
        settings["prediction_method"] = method
        settings["combinations"] = count
        self.app.save_settings()

        if method != "timesfm":
            self._show(predict(draws, method=method, combinations=count,
                               window=settings.get("frequency_window", DEFAULT_WINDOW)))
            return

        def work(report):
            forecaster = self.app.forecaster or TimesFMForecaster(
                checkpoint=settings.get("timesfm_checkpoint", ""),
                device=settings.get("timesfm_device", "cpu"),
                context_length=int(settings.get("context_length", 1024)),
                representation=settings.get("representation", "frequency"),
                window=int(settings.get("frequency_window", DEFAULT_WINDOW)),
                hf_token=settings.get("hf_token", ""),
            )
            if not forecaster.load_model(report):
                raise RuntimeError(
                    "TimesFM could not be loaded. Install it with "
                    "`pip install timesfm[torch]`, or pick another method — they all "
                    "score the same."
                )
            self.app.forecaster = forecaster
            return predict(draws, method="timesfm", combinations=count,
                           forecaster=forecaster, progress=report)

        self.app.run_worker("TimesFM forecast", work, self._show)

    def _show(self, prediction) -> None:
        self._prediction = prediction
        log_prediction(prediction.to_log_entry())
        for child in self.balls.winfo_children():
            child.destroy()
        for i, combination in enumerate(prediction.combinations, 1):
            line = ctk.CTkFrame(self.balls, fg_color="transparent")
            line.pack(fill="x", pady=3)
            ctk.CTkLabel(line, text=f"{i}.", width=24, text_color=MUTED).pack(side="left")
            ball_row(line, combination).pack(side="left")
        self.note.configure(text=prediction.note)

        ranked = prediction.ranked
        lines = [
            f"Method: {prediction.method}   Archive: {prediction.archive_size:,} draws "
            f"up to {prediction.archive_last_date}",
            "",
            "Top 15 by score",
            f"{'rank':>4} {'n':>3} {'score':>14}",
            "─" * 24,
        ]
        for rank, n in enumerate(ranked[:15], 1):
            lines.append(f"{rank:>4} {n:>3} {prediction.scores[n]:>14.6f}")
        lines += [
            "",
            "Bottom 5 by score, for scale",
            f"{'rank':>4} {'n':>3} {'score':>14}",
            "─" * 24,
        ]
        for rank, n in enumerate(ranked[-5:], len(ranked) - 4):
            lines.append(f"{rank:>4} {n:>3} {prediction.scores[n]:>14.6f}")
        spread = prediction.scores[ranked[0]] - prediction.scores[ranked[-1]]
        lines += [
            "",
            f"Score spread across all ninety numbers: {spread:.6f}.",
            "",
            value_note(),
        ]
        self.box.set_text("\n".join(lines))
        self.app.set_status(
            f"{len(prediction.combinations)} combinations from {prediction.method}."
        )

    def refresh(self) -> None:
        pass
