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
from core.localise import it_count, it_date, it_number
from core.predictor import (
    METHODS,
    SUPERSTAR_ODDS,
    expected_hits,
    predict,
    system_columns,
    system_profile,
    system_top_prize_odds,
    ticket_cost,
    value_note,
)
from gui.theme import BG_ROOT, MUTED
from gui.widgets import ReportBox, ball_row, section

_METHOD_LABELS = {
    "timesfm": "TimesFM 3.0 (modello fondazionale da 330M)",
    "frequenza": "Frequenza (i più estratti di recente)",
    "ritardo": "Ritardo (assenti da più tempo)",
    "casuale": "Casuale (la condizione di controllo)",
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

    Printed under every prediction because the two settings that shape it —
    the system size and the SuperStar — live on another tab, and a user who
    set them last week should not have to go back and check what they chose.
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
            f"SuperStar giocato: {prediction.superstar}. Esce da un'urna separata, "
            f"quindi indovinarlo è 1 su {SUPERSTAR_ODDS} qualunque numero si scelga "
            "e qualunque cosa facciano i sei.",
        ]
    return lines


class PredictionPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_ROOT)
        self.app = app
        self._prediction = None
        self._build()

    def _build(self) -> None:
        controls = section(
            self, "Passo 4 di 4 · Genera le combinazioni",
            "Il punto di arrivo. Scegli un metodo, quante combinazioni vuoi, e premi "
            "«Genera».\n"
            "Ogni metodo qui sotto ha lo stesso punteggio atteso, perché "
            "l'estrazione da prevedere è indipendente da tutto ciò che guardano. "
            "Il passo 3 lo misura sui dati veri.\n"
            "Quanti numeri per combinazione e se giocare il SuperStar si scelgono "
            "nelle Impostazioni.\n"
            "Una combinazione sola è quasi sempre la scelta giusta: la seconda è la "
            "settima scelta del metodo al posto della sesta, la terza l'ottava, e "
            "così via scendendo lungo la graduatoria.",
        )
        controls.pack(fill="x", padx=16, pady=(16, 8))
        row = ctk.CTkFrame(controls.body, fg_color="transparent")
        row.pack(fill="x")

        ctk.CTkLabel(row, text="Metodo", text_color=MUTED).pack(side="left", padx=(0, 6))
        self.method = ctk.CTkOptionMenu(
            row, width=330, values=[_METHOD_LABELS[m] for m in METHODS]
        )
        self.method.set(
            _METHOD_LABELS[self.app.settings.get("prediction_method", "frequenza")]
        )
        self.method.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row, text="Combinazioni", text_color=MUTED).pack(side="left", padx=(0, 6))
        self.count = ctk.CTkOptionMenu(row, width=70, values=[str(i) for i in range(1, 11)])
        self.count.set(str(self.app.settings.get("combinations", 1)))
        self.count.pack(side="left", padx=(0, 16))

        ctk.CTkButton(row, text="Genera", width=120, command=self._generate).pack(side="left")

        self.note = ctk.CTkLabel(
            controls.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=1000
        )
        self.note.pack(fill="x", pady=(10, 0))

        self.output = section(self, "Combinazioni")
        self.output.pack(fill="x", padx=16, pady=8)
        self.balls = ctk.CTkFrame(self.output.body, fg_color="transparent")
        self.balls.pack(fill="x")

        detail = section(self, "Punteggi e probabilità")
        detail.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.box = ReportBox(detail.body, height=240)
        self.box.pack(fill="both", expand=True)
        self.box.set_text(value_note())

    def _selected_method(self) -> str:
        label = self.method.get()
        for key, text in _METHOD_LABELS.items():
            if text == label:
                return key
        return "frequenza"

    def _generate(self) -> None:
        draws = self.app.draws
        if not draws:
            self.app.set_status("Ancora nessun archivio — scaricalo dalla scheda Archivio.")
            return
        method = self._selected_method()
        count = int(self.count.get())
        settings = self.app.settings
        settings["prediction_method"] = method
        settings["combinations"] = count
        self.app.save_settings()

        size = int(settings.get("prediction_size", 6))
        star = bool(settings.get("predict_superstar", False))

        if method != "timesfm":
            self._show(predict(draws, method=method, combinations=count, size=size,
                               superstar=star,
                               window=settings.get("frequency_window", DEFAULT_WINDOW)))
            return

        def work(report):
            forecaster = self.app.forecaster or TimesFMForecaster(
                checkpoint=settings.get("timesfm_checkpoint", ""),
                device=settings.get("timesfm_device", "cpu"),
                context_length=int(settings.get("context_length", 1024)),
                representation=settings.get("representation", "frequenza"),
                window=int(settings.get("frequency_window", DEFAULT_WINDOW)),
                hf_token=settings.get("hf_token", ""),
            )
            if not forecaster.load_model(report):
                raise RuntimeError(
                    "TimesFM non si è caricato. Installalo con "
                    "`pip install timesfm[torch]`, oppure scegli un altro metodo: "
                    "ottengono tutti lo stesso punteggio."
                )
            self.app.forecaster = forecaster
            return predict(draws, method="timesfm", combinations=count, size=size,
                           superstar=star, forecaster=forecaster, progress=report)

        self.app.run_worker("TimesFM forecast", work, self._show)

    def _show(self, prediction) -> None:
        self._prediction = prediction
        self.app.last_prediction = prediction          # step 4, for the path panel
        log_prediction(prediction.to_log_entry())
        for child in self.balls.winfo_children():
            child.destroy()
        for i, combination in enumerate(prediction.combinations, 1):
            line = ctk.CTkFrame(self.balls, fg_color="transparent")
            line.pack(fill="x", pady=3)
            ctk.CTkLabel(line, text=f"{i}.", width=24, text_color=MUTED).pack(side="left")
            ball_row(line, combination).pack(side="left")
        if prediction.superstar is not None:
            line = ctk.CTkFrame(self.balls, fg_color="transparent")
            line.pack(fill="x", pady=(8, 3))
            ctk.CTkLabel(
                line, text="SuperStar", width=90, anchor="w", text_color=MUTED,
            ).pack(side="left")
            ball_row(line, (prediction.superstar,)).pack(side="left")
        shape = f"{prediction.size} numeri per combinazione"
        if prediction.size > 6:
            shape += f" — sistema da {it_number(system_columns(prediction.size))} colonne"
        if prediction.superstar is not None:
            shape += ", SuperStar compreso"
        cost = ticket_cost(
            prediction.combinations,
            superstar=prediction.superstar is not None,
            column_price=float(self.app.settings.get("column_price", 1.0)),
            superstar_price=float(self.app.settings.get("superstar_price", 0.5)),
        )
        self.note.configure(
            text=f"{prediction.note}  ·  {shape}. "
            f"Costo: {it_number(cost.total, 2)} euro. "
            f"Punteggio atteso dal caso: {expected_hits(prediction.size):.3f} "
            "numeri indovinati per estrazione."
        )

        ranked = prediction.ranked
        lines = [
            f"Metodo: {prediction.method}   Archivio: "
            f"{it_number(prediction.archive_size)} estrazioni fino al "
            f"{it_date(prediction.archive_last_date)}",
            "",
            "I 15 col punteggio più alto",
            f"{'pos.':>5} {'n':>3} {'punteggio':>14}",
            "─" * 25,
        ]
        for rank, n in enumerate(ranked[:15], 1):
            lines.append(f"{rank:>5} {n:>3} {prediction.scores[n]:>14.6f}")
        lines += [
            "",
            "Gli ultimi 5, per avere la scala",
            f"{'pos.':>5} {'n':>3} {'punteggio':>14}",
            "─" * 25,
        ]
        for rank, n in enumerate(ranked[-5:], len(ranked) - 4):
            lines.append(f"{rank:>5} {n:>3} {prediction.scores[n]:>14.6f}")
        spread = prediction.scores[ranked[0]] - prediction.scores[ranked[-1]]
        lines += [
            "",
            f"Escursione dei punteggi sui novanta numeri: {spread:.6f}.",
            "",
        ]
        lines += _ticket_lines(prediction)
        settings = self.app.settings
        cost = ticket_cost(
            prediction.combinations,
            superstar=prediction.superstar is not None,
            column_price=float(settings.get("column_price", 1.0)),
            superstar_price=float(settings.get("superstar_price", 0.5)),
        )
        lines += ["", *_cost_lines(prediction, cost)]
        lines += ["", value_note()]
        self.box.set_text("\n".join(lines))
        self.app.set_status(
            f"{len(prediction.combinations)} combinazioni dal metodo "
            f"{prediction.method}."
        )

    def refresh(self) -> None:
        pass
