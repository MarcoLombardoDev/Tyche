# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
prediction_panel.py — Tyche

Generates the combinations, with all four methods side by side.

**There is no method selector, and that is the change 0.10.0 made.** Choosing
one meant seeing one, which quietly turned the four methods into a preference:
pick the one you trust, get its numbers, and never find out that the other
three — the random control included — produce a ticket that looks exactly as
convincing and scores exactly the same. Running all four every time and
showing them in one window makes that visible without a word of warning text.

It is also why the random baseline keeps its quarter of the screen, at the
same size as TimesFM's, and why a change that hides it would take the panel's
argument with it. A user who can see 330 million parameters and a random
number generator disagree about which six numbers to play, and knows both are
worth the same, has been told something no banner conveys.

The four cells hold what actually differs between methods: the combinations
and the scores behind them. What does not differ — the cost, the shape of the
ticket, the odds — is printed once above them, because four identical copies
of the same paragraph is noise, not symmetry.
"""

from __future__ import annotations

import textwrap

import customtkinter as ctk

from core.data_manager import log_prediction
from core.features import DEFAULT_WINDOW
from core.forecaster import TimesFMForecaster
from core.localise import it_count, it_date, it_number
from core.predictor import (
    METHODS,
    SUPERSTAR_ODDS,
    expected_hits,
    method_name,
    predict,
    system_columns,
    system_profile,
    system_top_prize_odds,
    ticket_cost,
    value_note,
)
from core.version import DEFAULT_TIMESFM_CHECKPOINT
from gui.model_status import ModelStatus
from gui.theme import ACCENT, BG_ROOT, MUTED, TEXT, WARN
from gui.widgets import ReportBox, ball_row, section

_METHOD_LABELS = {
    "timesfm": "TimesFM 3.0 (modello fondazionale da 330M)",
    "frequenza": "Frequenza (i più estratti di recente)",
    "ritardo": "Ritardo (assenti da più tempo)",
    "casuale": "Casuale (la condizione di controllo)",
}

# What each cell says under the method's name. Short: the cell is a quarter of
# the window and the numbers are the point.
_METHOD_BLURBS = {
    "timesfm": "prevede la serie di ogni numero",
    "frequenza": "i più estratti di recente",
    "ritardo": "assenti da più tempo",
    "casuale": "condizione di controllo",
}


def _wrap(text: str, width: int = 116) -> str:
    """Fold a paragraph for the fixed-width strip, which does not wrap itself.

    ``ReportBox`` is monospaced with ``wrap="none"`` because it holds tables.
    A paragraph dropped into it becomes one very long line and a horizontal
    scrollbar under everything else.
    """
    return "\n".join(textwrap.wrap(text, width=width))


def _cost_lines(prediction, cost) -> list[str]:
    """What the plays on screen would cost, and what the money actually buys.

    Money is formatted the Italian way, comma for the decimal — unlike the
    statistics elsewhere, which keep the full stop because they sit beside
    chi-square and p-values. A price is not a test statistic.
    """
    lines = [
        f"Costo della giocata: {it_number(cost.total, 2)} euro"
        + (" (SuperStar compreso)." if cost.superstar else "."),
        f"  {it_count(cost.plays, 'giocata', 'giocate')} da {cost.size} numeri = "
        f"{it_count(cost.columns_paid, 'colonna', 'colonne')}.",
    ]
    if cost.plays > 1:
        lines.append(
            f"  Le combinazioni oltre la prima sono le scelte successive del "
            f"metodo — la {cost.plays}ª è la sua {cost.size + cost.plays - 1}ª "
            "preferenza. Non valgono di più per euro speso, e se il metodo "
            "sapesse qualcosa varrebbero di meno."
        )
    if cost.duplicated:
        share = cost.duplicated / cost.columns_paid
        lines += [
            f"  Ma le colonne diverse sono {it_number(cost.columns_distinct)}: "
            f"{it_number(cost.duplicated)} vengono pagate due volte, "
            f"il {share:.0%} della spesa.",
            "  Le combinazioni scorrono di un posto lungo la graduatoria, quindi "
            "si sovrappongono. Giocandone una sola non si spreca niente.",
        ]
    return lines


def _ticket_lines(prediction) -> list[str]:
    """What the ticket on screen actually is, in columns and in odds.

    Printed once for the whole page rather than per method: the size and the
    SuperStar come from the settings, so every one of the four tickets has the
    same shape and the same price.
    """
    size = prediction.size
    lines = []
    if size == 6:
        lines.append(
            f"Colonna singola da sei numeri: 1 possibilità su "
            f"{it_number(system_top_prize_odds(6))} di prendere il 6."
        )
    else:
        columns = system_columns(size)
        lines += [
            f"Sistema integrale da {size} numeri: copre {it_number(columns)} colonne, "
            f"quindi costa {it_number(columns)} volte una giocata singola.",
            f"Con {size} numeri il 6 è 1 possibilità su "
            f"{it_number(system_top_prize_odds(size))}, contro 1 su "
            f"{it_number(system_top_prize_odds(6))} di una colonna sola.",
            "",
            "Le due cose crescono nella stessa identica proporzione: la probabilità "
            "per euro giocato non cambia di una virgola.",
            "Un sistema è un modo di spendere di più, non di guadagnare di più.",
            "",
            "Quello che un sistema compra davvero sono le vincite minori che "
            "accompagnano quella grande. Indovinando tutti e sei i numeri:",
            f"  {'indovinati':>10}  {'colonne vincenti':>17}",
        ]
        for matched, columns_won in sorted(
            system_profile(size, 6).items(), reverse=True
        ):
            lines.append(f"  {matched:>10}  {it_number(columns_won):>17}")
    if prediction.superstar is not None:
        lines += [
            "",
            f"Il SuperStar esce da un'urna separata, quindi indovinarlo è 1 su "
            f"{SUPERSTAR_ODDS} qualunque numero si scelga e qualunque cosa "
            "facciano i sei.",
        ]
    return lines


class _MethodCell(ctk.CTkFrame):
    """One quarter of the page: a method's combinations and its scores."""

    def __init__(self, parent, method: str):
        super().__init__(parent, fg_color=BG_ROOT)
        self.method = method
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text=method_name(method), anchor="w", text_color=ACCENT,
        ).pack(side="left")
        ctk.CTkLabel(
            header, text=f" — {_METHOD_BLURBS[method]}", anchor="w", text_color=MUTED,
        ).pack(side="left")

        # height=0 because an empty CTkFrame requests 200x200, and a cell whose
        # method produced nothing would reserve 200px for the balls it does not
        # have — the same default that once made every path card 200px tall.
        self.balls = ctk.CTkFrame(self, fg_color="transparent", height=0)
        self.balls.pack(fill="x", pady=(4, 0))
        self.state = ctk.CTkLabel(
            self, text="", anchor="w", justify="left", text_color=MUTED, wraplength=520,
        )
        self.state.pack(fill="x")
        self.box = ReportBox(self, height=120)
        self.box.pack(fill="both", expand=True, pady=(4, 0))

    def clear(self, message: str, colour: str = MUTED) -> None:
        for child in self.balls.winfo_children():
            child.destroy()
        self.state.configure(text=message, text_color=colour)
        self.box.set_text("")

    def show(self, prediction) -> None:
        for child in self.balls.winfo_children():
            child.destroy()
        self.state.configure(text="")
        for i, combination in enumerate(prediction.combinations, 1):
            line = ctk.CTkFrame(self.balls, fg_color="transparent")
            line.pack(fill="x", pady=2)
            ctk.CTkLabel(line, text=f"{i}.", width=20, text_color=MUTED).pack(side="left")
            ball_row(line, combination, size=30).pack(side="left")
        if prediction.superstar is not None:
            line = ctk.CTkFrame(self.balls, fg_color="transparent")
            line.pack(fill="x", pady=(6, 2))
            ctk.CTkLabel(
                line, text="SuperStar", width=72, anchor="w", text_color=MUTED,
            ).pack(side="left")
            ball_row(line, (prediction.superstar,), size=30).pack(side="left")
        self.box.set_text("\n".join(_score_lines(prediction)))


def _score_lines(prediction) -> list[str]:
    """The part of a prediction that really is the method's own."""
    ranked = prediction.ranked
    spread = prediction.scores[ranked[0]] - prediction.scores[ranked[-1]]
    # The spread leads, because it is the one number that says how much this
    # method actually distinguishes between the ninety — and reading TimesFM's
    # against the frequency baseline's is how you find out they agree.
    lines = [
        f"Escursione sui novanta numeri: {spread:.6f}",
        "",
        f"{'pos.':>5} {'n':>3} {'punteggio':>14}",
        "─" * 25,
    ]
    for rank, n in enumerate(ranked[:10], 1):
        lines.append(f"{rank:>5} {n:>3} {prediction.scores[n]:>14.6f}")
    lines += [
        "  …",
        f"{'':>5} {'':>3} {'':>14}".rstrip(),
        "gli ultimi tre, per avere la scala",
    ]
    for rank, n in enumerate(ranked[-3:], len(ranked) - 2):
        lines.append(f"{rank:>5} {n:>3} {prediction.scores[n]:>14.6f}")
    lines += ["", prediction.note]
    return lines


class PredictionPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._predictions: dict = {}
        self._cells: dict[str, _MethodCell] = {}
        self._build()

    def _build(self) -> None:
        controls = section(
            self, "Genera le combinazioni",
            "Premi «Genera»: i quattro metodi girano insieme, uno per riquadro. "
            "Sono affiancati di proposito — hanno tutti lo stesso punteggio atteso, "
            "compreso quello casuale, che è lì per questo.\n"
            "Numeri per combinazione e SuperStar si scelgono nelle Impostazioni.",
        )
        controls.pack(fill="x", padx=16, pady=(16, 8))

        row = ctk.CTkFrame(controls.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Combinazioni", text_color=MUTED).pack(side="left", padx=(0, 6))
        self.count = ctk.CTkOptionMenu(row, width=70, values=[str(i) for i in range(1, 11)])
        self.count.set(str(self.app.settings.get("combinations", 1)))
        self.count.pack(side="left", padx=(0, 16))
        ctk.CTkButton(row, text="Genera", width=120, command=self._generate).pack(side="left")
        ctk.CTkLabel(
            row,
            text=(
                "Una combinazione sola è quasi sempre la scelta giusta: la seconda è "
                "la settima scelta del metodo al posto della sesta, e così via."
            ),
            text_color=MUTED,
        ).pack(side="left", padx=14)

        self.model_status = ModelStatus(controls.body, self.app)
        self.model_status.pack(fill="x", pady=(8, 0))

        # One line here and the rest below the grid: what the four tickets
        # have in common must not push the four tickets off the screen, which
        # is what the first version of this layout did.
        self.note = ctk.CTkLabel(
            controls.body, text="", anchor="w", justify="left",
            text_color=TEXT, wraplength=1180,
        )
        self.note.pack(fill="x", pady=(8, 0))

        # Packed before the grid and to the bottom: pack gives the expanding
        # widget whatever is left, and a strip packed after it is simply
        # clipped off the window when the four cells are hungry.
        self.detail = ReportBox(self, height=104)
        self.detail.pack(side="bottom", fill="x", padx=22, pady=(4, 14))
        self.detail.set_text(_wrap(value_note()))

        grid = ctk.CTkFrame(self, fg_color=BG_ROOT)
        grid.pack(fill="both", expand=True, padx=16, pady=(0, 0))
        for column in (0, 1):
            grid.grid_columnconfigure(column, weight=1, uniform="method")
        for line in (0, 1):
            grid.grid_rowconfigure(line, weight=1, uniform="method")
        for index, method in enumerate(METHODS):
            cell = _MethodCell(grid, method)
            cell.grid(
                row=index // 2, column=index % 2, sticky="nsew", padx=6, pady=6,
            )
            self._cells[method] = cell
            cell.clear("Non ancora generate.")

    # ── running ──────────────────────────────────────────────
    def _generate(self) -> None:
        draws = self.app.draws
        if not draws:
            self.app.set_status("Ancora nessun archivio — scaricalo dalla scheda Archivio.")
            return
        count = int(self.count.get())
        settings = self.app.settings
        settings["combinations"] = count
        self.app.save_settings()

        size = int(settings.get("prediction_size", 6))
        star = bool(settings.get("predict_superstar", False))
        window = int(settings.get("frequency_window", DEFAULT_WINDOW))
        with_model = self.model_status.available

        def work(report):
            forecaster = None
            skipped = ""
            if with_model:
                forecaster = self.app.forecaster or TimesFMForecaster(
                    checkpoint=(
                        settings.get("timesfm_checkpoint") or DEFAULT_TIMESFM_CHECKPOINT
                    ),
                    device=settings.get("timesfm_device", "cpu"),
                    context_length=int(settings.get("context_length", 1024)),
                    representation=settings.get("representation", "frequenza"),
                    window=window,
                    hf_token=settings.get("hf_token", ""),
                )
                if forecaster.load_model(report):
                    self.app.forecaster = forecaster
                else:
                    # The other three still have something to say, so a model
                    # that will not load costs its own cell and nothing else.
                    forecaster = None
                    skipped = "TimesFM non si è caricato."
            results = {}
            for method in METHODS:
                if method == "timesfm" and forecaster is None:
                    continue
                report(f"{method_name(method)}…", 0.0)
                results[method] = predict(
                    draws, method=method, combinations=count, size=size,
                    superstar=star, window=window,
                    forecaster=forecaster if method == "timesfm" else None,
                    progress=report if method == "timesfm" else None,
                )
            return results, skipped

        self.app.run_worker("Previsione", work, self._show)

    # ── output ───────────────────────────────────────────────
    def _show(self, result) -> None:
        predictions, skipped = result
        self._predictions = predictions
        self.app.last_predictions = predictions
        for prediction in predictions.values():
            log_prediction(prediction.to_log_entry())

        for method, cell in self._cells.items():
            if method in predictions:
                cell.show(predictions[method])
            elif method == "timesfm":
                # Its own sentence, not the strip's: that label is empty until
                # the tab has been shown once, and the first version of this
                # left the cell blank on a machine without the weights.
                cell.clear(
                    skipped
                    or "TimesFM non è disponibile: mancano i pesi, oppure il "
                    "pacchetto non è installato in questa copia. Vedi la riga "
                    "qui sopra.",
                    WARN,
                )
            else:
                cell.clear("Non generata.")

        if not predictions:
            self.note.configure(text="")
            self.app.set_status("Nessun metodo ha prodotto una previsione.")
            return

        any_prediction = next(iter(predictions.values()))
        cost = ticket_cost(
            any_prediction.combinations,
            superstar=any_prediction.superstar is not None,
            column_price=float(self.app.settings.get("column_price", 1.0)),
            superstar_price=float(self.app.settings.get("superstar_price", 0.5)),
        )
        self.note.configure(
            text=(
                f"Archivio: {it_number(any_prediction.archive_size)} estrazioni fino "
                f"al {it_date(any_prediction.archive_last_date)}.  ·  "
                f"Costo: {it_number(cost.total, 2)} euro — quello di UNA delle "
                "quattro proposte qui sotto, che sono alternative e non una giocata "
                "da moltiplicare per quattro.  ·  "
                f"Punteggio atteso dal caso, per tutte e quattro: "
                f"{expected_hits(any_prediction.size):.3f} numeri indovinati "
                "per estrazione."
            )
        )
        lines = _ticket_lines(any_prediction)
        lines += ["", *_cost_lines(any_prediction, cost)]
        lines += ["", _wrap(value_note())]
        self.detail.set_text("\n".join(lines))
        self.app.set_status(
            f"{it_count(len(predictions), 'metodo', 'metodi')} a confronto, "
            f"{it_count(len(any_prediction.combinations), 'combinazione', 'combinazioni')} "
            "ciascuno."
        )

    def refresh(self) -> None:
        # Every tab switch: the weights may have arrived from the path panel.
        self.model_status.refresh()
