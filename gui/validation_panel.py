# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
validation_panel.py — Tyche

Runs the walk-forward backtest and prints the table.

The baselines are ticked by default and TimesFM is not, because the baselines
take under a second and the model takes one forward pass per scored draw. The
ordering is also the argument: see the three cheap methods tie with chance
first, and the expensive one becomes a confirmation rather than a hope.
"""

from __future__ import annotations

import customtkinter as ctk

from core.forecaster import TimesFMForecaster
from core.predictor import METHODS
from core.validation import walk_forward
from gui.theme import BG_ROOT, GOOD, MUTED, WARN
from gui.widgets import ReportBox, section


class ValidationPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._checks: dict[str, ctk.CTkCheckBox] = {}
        self._build()

    def _build(self) -> None:
        controls = section(
            self, "Walk-forward backtest",
            "Step through the most recent draws. At each step a method sees only the "
            "draws before it, picks six numbers, and is scored against what came out. "
            "Chance is 0.4 hits per draw, exactly.",
        )
        controls.pack(fill="x", padx=16, pady=(16, 8))

        row = ctk.CTkFrame(controls.body, fg_color="transparent")
        row.pack(fill="x")
        for method in METHODS:
            box = ctk.CTkCheckBox(row, text=method, width=90)
            if method != "timesfm":
                box.select()
            box.pack(side="left", padx=(0, 14))
            self._checks[method] = box

        row2 = ctk.CTkFrame(controls.body, fg_color="transparent")
        row2.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(row2, text="Draws to score", text_color=MUTED).pack(side="left", padx=(0, 6))
        self.n_draws = ctk.CTkEntry(row2, width=90)
        self.n_draws.insert(0, str(self.app.settings.get("validation_draws", 300)))
        self.n_draws.pack(side="left", padx=(0, 16))
        ctk.CTkButton(row2, text="Run", width=120, command=self._run).pack(side="left")
        ctk.CTkLabel(
            row2,
            text="TimesFM costs one model call per draw — start small.",
            text_color=MUTED,
        ).pack(side="left", padx=14)

        self.verdict = ctk.CTkLabel(
            controls.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=1000
        )
        self.verdict.pack(fill="x", pady=(10, 0))

        results = section(self, "Results")
        results.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.box = ReportBox(results.body, height=340)
        self.box.pack(fill="both", expand=True)

    def _run(self) -> None:
        draws = self.app.draws
        if not draws:
            self.app.set_status("No archive yet — fetch one from the Archive tab.")
            return
        methods = [m for m, box in self._checks.items() if box.get()]
        if not methods:
            self.app.set_status("Tick at least one method.")
            return
        try:
            n_draws = int(self.n_draws.get())
        except ValueError:
            self.app.set_status("Draws to score must be a whole number.")
            return
        settings = self.app.settings
        settings["validation_draws"] = n_draws
        self.app.save_settings()

        def work(report):
            forecaster = None
            if "timesfm" in methods:
                forecaster = self.app.forecaster or TimesFMForecaster(
                    checkpoint=settings.get("timesfm_checkpoint", ""),
                    device=settings.get("timesfm_device", "cpu"),
                    context_length=int(settings.get("context_length", 1024)),
                    representation=settings.get("representation", "frequency"),
                    window=int(settings.get("frequency_window", 150)),
                    hf_token=settings.get("hf_token", ""),
                )
                if not forecaster.load_model(report):
                    raise RuntimeError(
                        "TimesFM could not be loaded — untick it, or install it with "
                        "`pip install timesfm[torch]`."
                    )
                self.app.forecaster = forecaster
            return walk_forward(
                draws, methods=methods, n_draws=n_draws,
                forecaster=forecaster,
                window=int(settings.get("frequency_window", 150)),
                progress=report,
            )

        self.app.run_worker("Validation", work, self._show)

    def _show(self, report) -> None:
        header = (
            f"{'method':<11} {'hits/draw':>10} {'chance':>8} {'total':>7} "
            f"{'vs chance':>10} {'z':>7} {'p':>7} {'best':>5} {'>=3':>5} {'exp>=3':>7}"
        )
        lines = [
            f"{report.draws_scored} draws scored, {report.first_target.date} to "
            f"{report.last_target.date}, {report.picks_per_draw} picks each.",
            "",
            header,
            "─" * len(header),
        ]
        for r in report.results:
            lines.append(
                f"{r.method:<11} {r.mean_hits:>10.4f} {r.expected_mean:>8.4f} "
                f"{r.total_hits:>7} {r.excess:>+10.1f} {r.z:>+7.2f} {r.p_value:>7.3f} "
                f"{r.best_draw_hits:>5} {r.three_or_more:>5} {r.expected_three_or_more:>7.1f}"
            )
        lines += ["", "Distribution of hits per draw, against the chance distribution", ""]
        picks = report.picks_per_draw
        lines.append("  " + " ".join(f"{k:>7}" for k in range(picks + 1)))
        for r in report.results:
            lines.append(f"{r.method:<11}" + " ".join(f"{h:>7}" for h in r.histogram))
            lines.append(
                f"{'  chance χ²':<11}"
                + f"  {r.chi2:.2f} on {r.chi2_dof} dof, p = {r.chi2_p:.3f}"
            )
        self.box.set_text("\n".join(lines))
        beat = any(r.p_value < 0.05 and r.z > 0 for r in report.results)
        self.verdict.configure(text=report.verdict(), text_color=WARN if beat else GOOD)
        self.app.set_status(f"Validation over {report.draws_scored} draws complete.")

    def refresh(self) -> None:
        pass
