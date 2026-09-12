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
and the scores behind them. What does not differ — the archive, the cost, the
shape of the ticket, the odds — is printed once *below* them, in one block,
because four identical copies of the same paragraph is noise and a second
strip above the grid was one place too many to look.
"""

from __future__ import annotations

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
from gui.theme import ACCENT, BG_PANEL, BG_ROOT, MUTED, WARN
from gui.widgets import (
    ReportBox,
    ball_row,
    body_font,
    fit_text,
    heading_font,
    section,
    star_badge,
)

_METHOD_LABELS = {
    "timesfm": "TimesFM 3.0 (modello fondazionale da 330M)",
    "frequenza": "Frequenza (i più estratti di recente)",
    "ritardo": "Ritardo (assenti da più tempo)",
    "casuale": "Casuale (la condizione di controllo)",
}

# How wide a number is on this screen, ball or star alike. **One constant for
# both**: they sit on the same row, and a SuperStar bigger than the six would
# read as more important than them rather than merely different. The size is
# driven by the star — its usable middle is a fraction of its bounding box, so
# 30 pixels leaves the number across the points instead of inside the shape —
# and the balls follow it.
BADGE_SIZE = 50


# What each cell says under the method's name. Short: the cell is a quarter of
# the window and the numbers are the point.
_METHOD_BLURBS = {
    "timesfm": "prevede la serie di ogni numero",
    "frequenza": "i più estratti di recente",
    "ritardo": "assenti da più tempo",
    "casuale": "condizione di controllo",
}


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
    """One method's answer: the numbers, and nothing else.

    **The scores used to be in here and are now in the report beside it.**
    Four dark boxes of tables stacked down the page put the thing the user
    came for — six numbers — in a fifth of the space and the arithmetic in the
    other four fifths. The tables did not become less important; they moved to
    where there is room to read them, which is a column of their own.
    """

    def __init__(self, parent, method: str):
        # A frame with Tyche's own colour round it. Four cells on one dark
        # background read as one continuous page of text, which is what the
        # owner saw: the borders are what say "these are four separate
        # answers to the same question".
        super().__init__(
            parent, fg_color=BG_PANEL, border_color=ACCENT, border_width=1,
            corner_radius=8,
        )
        self.method = method
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            header, text=method_name(method), anchor="w", text_color=ACCENT,
            font=heading_font(14),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text=f" — {_METHOD_BLURBS[method]}", anchor="w",
            text_color=MUTED, font=body_font(),
        ).pack(side="left")

        # height=0 because an empty CTkFrame requests 200x200, and a cell whose
        # method produced nothing would reserve 200px for the balls it does not
        # have — the same default that once made every path card 200px tall.
        self.balls = ctk.CTkFrame(self, fg_color="transparent", height=0)
        self.balls.pack(fill="x", padx=10, pady=(6, 0))
        self.state = fit_text(ctk.CTkLabel(
            self, text="", anchor="w", justify="left", text_color=MUTED,
            wraplength=520, font=body_font(),
        ))
        self.state.pack(fill="x", padx=10, pady=(0, 10))

    def clear(self, message: str, colour: str = MUTED) -> None:
        for child in self.balls.winfo_children():
            child.destroy()
        self.state.configure(text=message, text_color=colour)

    def show(self, prediction) -> None:
        for child in self.balls.winfo_children():
            child.destroy()
        self.state.configure(text="")
        for i, combination in enumerate(prediction.combinations, 1):
            line = ctk.CTkFrame(self.balls, fg_color="transparent")
            line.pack(fill="x", pady=2)
            ctk.CTkLabel(
                line, text=f"{i}.", width=20, text_color=MUTED, font=body_font(),
            ).pack(side="left", anchor="n", pady=(10, 0))
            ball_row(line, combination, size=BADGE_SIZE).pack(side="left")
            if i == 1 and prediction.superstar is not None:
                self._star(line, prediction.superstar)

    def _star(self, line, number: int) -> None:
        """The SuperStar, on the numbers' own row and right-aligned.

        **One widget, not two.** The first version put a ★ character beside an
        ordinary purple ball, which says "this one is the SuperStar" in two
        pieces where one will do; the badge is now a star-shaped thing with
        the number inside it.

        Packed *after* the combination and to the right, which is what makes
        "if there is room" true rather than a hope: pack hands the first
        widget its requested width and this one takes what is left, so a
        window too narrow for a twelve-number system loses the star and not
        the numbers.
        """
        # anchor="n" so it lines up with the *first* row of balls: a system of
        # twelve wraps onto two lines and a vertically centred star would sit
        # between them, pointing at nothing.
        star_badge(line, number, size=BADGE_SIZE, background=BG_PANEL).pack(
            side="right", padx=(6, 0), anchor="n",
        )


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


def _method_lines(predictions: dict, skipped: str) -> list[str]:
    """Every method's own numbers, under the text they all share.

    They used to be four separate boxes inside four cells. One report means
    one place to scroll and, more to the point, the four spreads end up on the
    same page — which is how a reader finds out that two methods that look
    different are ranking the ninety numbers almost identically.

    Built from :data:`METHODS` rather than from ``predictions``, so a method
    that produced nothing says so here instead of vanishing from the
    comparison.
    """
    lines = ["═" * 46, "I punteggi, metodo per metodo", ""]
    for method in METHODS:
        lines.append(f"── {method_name(method)} " + "─" * 24)
        if method in predictions:
            lines += _score_lines(predictions[method])
        elif method == "timesfm":
            lines.append(skipped or "Non eseguito: il modello non è disponibile.")
        else:
            lines.append("Non eseguito.")
        lines.append("")
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
        ctk.CTkLabel(
            row, text="Combinazioni", text_color=MUTED, font=body_font(),
        ).pack(side="left", padx=(0, 6))
        self.count = ctk.CTkOptionMenu(row, width=70, values=[str(i) for i in range(1, 11)])
        self.count.set(str(self.app.settings.get("combinations", 1)))
        self.count.pack(side="left", padx=(0, 16))
        self.button = ctk.CTkButton(
            row, text="Genera", width=120, command=self._generate,
        )
        self.button.pack(side="left")

        # Beside the button, and *only when something is wrong*. The strip
        # used to say "TimesFM è pronto" there, which is a line the reader has
        # to process on every visit to learn that nothing needs doing. When it
        # is not ready it says so and sends the reader to the path, which is
        # the screen that can actually fix it.
        # No download button here either — step 2 of the path owns that one.
        self.model_status = ModelStatus(
            row, self.app, offer_download=False, errors_only=True,
        )
        self.model_status.pack(side="left", fill="x", expand=True, padx=14)

        # Two columns: the answers on the left, the working on the right.
        #
        # Before this the four cells were a 2x2 grid of half-output and
        # half-scores, with a shared block of prose underneath — so the six
        # numbers a reader came for took a fifth of each cell and the tables
        # took the rest, four times over. The numbers now stack down the left
        # in a column of their own, and everything that is text lives in one
        # report on the right where there is width to read it.
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        body.grid_rowconfigure(0, weight=1)
        for column in (0, 1):
            body.grid_columnconfigure(column, weight=1, uniform="half")

        # Scrollable: ten combinations of a twelve-number system is a column
        # taller than any window, and the cells must not shrink to fit.
        cells = ctk.CTkScrollableFrame(body, fg_color=BG_ROOT)
        cells.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        for method in METHODS:
            cell = _MethodCell(cells, method)
            cell.pack(fill="x", pady=(0, 10))
            self._cells[method] = cell
            cell.clear("Non ancora generate.")

        # The dark report. It wraps on words rather than being folded by hand,
        # so the prose uses the whole column; the tables appended to it are
        # narrower than that and do not need the width.
        self.report = ReportBox(body, wrap="word")
        self.report.grid(row=0, column=1, sticky="nsew")
        self.report.set_text(value_note())

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
                    hf_token=settings.get("hf_token", ""),
                    local_dir=settings.get("timesfm_local_dir", ""),
                )
                if forecaster.load_model(report):
                    self.app.forecaster = forecaster
                else:
                    # The other three still have something to say, so a model
                    # that will not load costs its own cell and nothing else —
                    # and it costs it *with the reason*, which used to be
                    # thrown away here and left the user with a bare "non si è
                    # caricato" under a path panel saying it was ready.
                    skipped = forecaster.last_error or "TimesFM non si è caricato."
                    forecaster = None
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

        # Disabled until this run ends, and re-enabled by on_done rather than
        # by _show: a run that raises never reaches _show, and a button that
        # comes back only on success is a button that dies the first time
        # something goes wrong. run_worker already refuses a second job, but
        # refusing it in the status bar after the click is not the same as
        # saying beforehand that the click will do nothing.
        self.button.configure(state="disabled", text="Generazione…")
        self.app.run_worker("Previsione", work, self._show, on_done=self._enable)

    def _enable(self) -> None:
        """Give the button back. Runs after every job, successful or not."""
        self.button.configure(state="normal", text="Genera")

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
                    "pacchetto non è installato in questa copia.",
                    WARN,
                )
            else:
                cell.clear("Non generata.")

        if not predictions:
            self.report.set_text(
                "Nessun metodo ha prodotto una previsione.\n\n"
                + (skipped or "")
            )
            self.app.set_status("Nessun metodo ha prodotto una previsione.")
            return

        any_prediction = next(iter(predictions.values()))
        cost = ticket_cost(
            any_prediction.combinations,
            superstar=any_prediction.superstar is not None,
            column_price=float(self.app.settings.get("column_price", 1.0)),
            superstar_price=float(self.app.settings.get("superstar_price", 0.5)),
        )
        lines = [
            f"Archivio: {it_number(any_prediction.archive_size)} estrazioni fino al "
            f"{it_date(any_prediction.archive_last_date)}. Punteggio atteso dal "
            f"caso, per tutte e quattro le proposte qui sopra: "
            f"{expected_hits(any_prediction.size):.3f} numeri indovinati per "
            "estrazione.",
            "",
            *_ticket_lines(any_prediction),
            "",
            *_cost_lines(any_prediction, cost),
            "Il costo è quello di UNA delle quattro proposte: sono alternative, "
            "non una giocata da moltiplicare per quattro.",
            "",
            value_note(),
            "",
            *_method_lines(predictions, skipped),
        ]
        self.report.set_text("\n".join(lines))
        self.app.set_status(
            f"{it_count(len(predictions), 'metodo', 'metodi')} a confronto, "
            f"{it_count(len(any_prediction.combinations), 'combinazione', 'combinazioni')} "
            "ciascuno."
        )

    def refresh(self) -> None:
        # Every tab switch: the weights may have arrived from the path panel.
        self.model_status.refresh()
