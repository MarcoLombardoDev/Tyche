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
from core.localise import it_date
from core.power import calibrate
from core.power import report as power_report
from core.predictor import METHODS
from core.scoring import MEAN_RANK
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
            self, "Backtest walk-forward",
            "Scorre le estrazioni più recenti. A ogni passo un metodo vede solo le "
            "estrazioni precedenti, sceglie sei numeri e viene confrontato con quello "
            "che è uscito. Il caso vale esattamente 0,4 centri per estrazione.",
        )
        controls.pack(fill="x", padx=16, pady=(16, 8))

        row = ctk.CTkFrame(controls.body, fg_color="transparent")
        row.pack(fill="x")
        # ``validation_baselines`` in settings, which is where a run's
        # selection is remembered. TimesFM is deliberately not in the default:
        # it costs one model call per scored draw, and the argument the panel
        # makes is that the cheap methods tie with chance first.
        selected = set(self.app.settings.get("validation_baselines") or [])
        for method in METHODS:
            box = ctk.CTkCheckBox(row, text=method, width=90)
            if method in selected:
                box.select()
            box.pack(side="left", padx=(0, 14))
            self._checks[method] = box

        row2 = ctk.CTkFrame(controls.body, fg_color="transparent")
        row2.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(
            row2, text="Estrazioni da valutare", text_color=MUTED
        ).pack(side="left", padx=(0, 6))
        self.n_draws = ctk.CTkEntry(row2, width=90)
        self.n_draws.insert(0, str(self.app.settings.get("validation_draws", 300)))
        self.n_draws.pack(side="left", padx=(0, 16))
        ctk.CTkButton(row2, text="Esegui", width=120, command=self._run).pack(side="left")
        ctk.CTkLabel(
            row2,
            text="TimesFM costa una chiamata al modello per estrazione — parti basso.",
            text_color=MUTED,
        ).pack(side="left", padx=14)

        # The calibration answers the question the table above cannot: whether
        # a run that found nothing was capable of finding anything. Its own
        # row, because it is a different experiment and not another method.
        row3 = ctk.CTkFrame(controls.body, fg_color="transparent")
        row3.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(
            row3, text="Calibra", width=120, command=self._calibrate,
        ).pack(side="left")
        ctk.CTkLabel(
            row3,
            text=(
                "Misura quanto piccolo dev'essere un vantaggio perché questa prova "
                "lo veda, iniettandone uno noto. Qualche decina di secondi."
            ),
            text_color=MUTED,
        ).pack(side="left", padx=14)

        self.verdict = ctk.CTkLabel(
            controls.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=1000
        )
        self.verdict.pack(fill="x", pady=(10, 0))

        results = section(self, "Risultati")
        results.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.box = ReportBox(results.body, height=340)
        self.box.pack(fill="both", expand=True)

    def _run(self) -> None:
        draws = self.app.draws
        if not draws:
            self.app.set_status("Ancora nessun archivio — scaricalo dalla scheda Archivio.")
            return
        methods = [m for m, box in self._checks.items() if box.get()]
        if not methods:
            self.app.set_status("Seleziona almeno un metodo.")
            return
        try:
            n_draws = int(self.n_draws.get())
        except ValueError:
            self.app.set_status("«Estrazioni da valutare» deve essere un numero intero.")
            return
        settings = self.app.settings
        settings["validation_draws"] = n_draws
        settings["validation_baselines"] = methods
        self.app.save_settings()

        def work(report):
            forecaster = None
            if "timesfm" in methods:
                forecaster = self.app.forecaster or TimesFMForecaster(
                    checkpoint=settings.get("timesfm_checkpoint", ""),
                    device=settings.get("timesfm_device", "cpu"),
                    context_length=int(settings.get("context_length", 1024)),
                    representation=settings.get("representation", "frequenza"),
                    window=int(settings.get("frequency_window", 150)),
                    hf_token=settings.get("hf_token", ""),
                )
                if not forecaster.load_model(report):
                    raise RuntimeError(
                        "TimesFM non si è caricato — toglilo dalla selezione, oppure "
                        "installalo con `pip install timesfm[torch]`."
                    )
                self.app.forecaster = forecaster
            return walk_forward(
                draws, methods=methods, n_draws=n_draws,
                forecaster=forecaster,
                window=int(settings.get("frequency_window", 150)),
                progress=report,
            )

        self.app.run_worker("Validation", work, self._show)

    def _calibrate(self) -> None:
        """Run the harness against edges of known size and print the floors."""
        draws = self.app.draws
        if not draws:
            self.app.set_status("Ancora nessun archivio — scaricalo dalla scheda Archivio.")
            return
        try:
            n_draws = int(self.n_draws.get())
        except ValueError:
            self.app.set_status("«Estrazioni da valutare» deve essere un numero intero.")
            return

        def work(report):
            return calibrate(draws, n_draws=n_draws, progress=report)

        self.app.run_worker("Calibration", work, self._show_calibration)

    def _show_calibration(self, points) -> None:
        self.box.set_text(power_report(points))
        self.verdict.configure(
            text=(
                "Questa è la sensibilità dello strumento, non un risultato "
                "sull'archivio. Dice quale vantaggio la prova qui sopra sarebbe "
                "riuscita a vedere — e, sulla forma «nascosto», che il conteggio "
                "dei centri da solo non ne vedrebbe nessuno."
            ),
            text_color=MUTED,
        )
        self.app.set_status("Calibrazione completata.")

    def _show(self, report) -> None:
        header = (
            f"{'metodo':<11} {'centri/estr':>12} {'caso':>7} {'totale':>7} "
            f"{'vs caso':>9} {'z':>7} {'p':>7} {'max':>4} {'>=3':>5} {'att.>=3':>8}"
        )
        lines = [
            f"{report.draws_scored} estrazioni valutate, dal "
            f"{it_date(report.first_target.date)} al "
            f"{it_date(report.last_target.date)}, {report.picks_per_draw} numeri "
            f"ciascuna.",
            "",
            header,
            "─" * len(header),
        ]
        for r in report.results:
            lines.append(
                f"{r.method:<11} {r.mean_hits:>12.4f} {r.expected_mean:>7.4f} "
                f"{r.total_hits:>7} {r.excess:>+9.1f} {r.z:>+7.2f} {r.p_value:>7.3f} "
                f"{r.best_draw_hits:>4} {r.three_or_more:>5} "
                f"{r.expected_three_or_more:>8.1f}"
            )
        lines += [
            "",
            "Distribuzione dei centri per estrazione, contro quella del caso",
            "",
        ]
        picks = report.picks_per_draw
        lines.append("  " + " ".join(f"{k:>7}" for k in range(picks + 1)))
        for r in report.results:
            lines.append(f"{r.method:<11}" + " ".join(f"{h:>7}" for h in r.histogram))
            lines.append(
                f"{'  χ² caso':<11}"
                + f"  {r.chi2:.2f} su {r.chi2_dof} gdl, p = {r.chi2_p:.3f}"
            )

        # The same run read on the whole ranking. The hit count above is blind
        # to any edge that never reaches the top six — core/power.py measures
        # exactly how blind — so this is printed beside it, never instead.
        rank_header = (
            f"{'metodo':<11} {'rango medio':>12} {'caso':>7} {'z':>8} {'p':>8} "
            f"{'top-10':>8} {'atteso':>8} {'top-20':>8} {'atteso':>8}"
        )
        lines += [
            "",
            "Sulla graduatoria completa dei novanta numeri, non solo sui primi sei",
            "",
            rank_header,
            "─" * len(rank_header),
        ]
        for r in report.results:
            lines.append(
                f"{r.method:<11} {r.mean_rank:>12.2f} {MEAN_RANK:>7.1f} "
                f"{r.rank_z:>+8.2f} {r.rank_p:>8.3f} "
                f"{r.top_hits.get(10, 0):>8} {r.expected_top_hits.get(10, 0):>8.0f} "
                f"{r.top_hits.get(20, 0):>8} {r.expected_top_hits.get(20, 0):>8.0f}"
            )

        self.box.set_text("\n".join(lines))
        beat = any(r.p_value < 0.05 and r.z > 0 for r in report.results)
        self.verdict.configure(text=report.verdict(), text_color=WARN if beat else GOOD)
        self.app.set_status(
            f"Validazione su {report.draws_scored} estrazioni completata."
        )

    def refresh(self) -> None:
        pass
