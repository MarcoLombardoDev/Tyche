# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
main.py — Tyche
Entry point. Opens the window, or answers a question and exits.

The command-line modes exist so the interesting parts of the program can be
run without a display — the reality check and the backtest are the parts worth
scripting, and neither needs a window:

    python main.py --version
    python main.py --check              # the five independence tests
    python main.py --validate 500       # walk-forward backtest, baselines only
    python main.py --power              # how small an edge the backtest can see
    python main.py --update             # refresh the archive (dry run)
    python main.py --update --yes       # ...and write it
    python main.py --import FILE --yes  # import a file you downloaded
    python main.py --forecast gap       # six numbers, no window
    python main.py --export-sqlite data/tyche.db

``--update`` and ``--import`` are dry runs unless ``--yes`` is given. That is
the same rule the Archive tab follows and it exists for the same reason: the
HTML scraper has never been checked against a real page, the archive has no
undo, and a cron job that writes whatever it parsed is the one shape of this
feature that can quietly destroy the history.

``--version`` is handled before ``gui.app`` is imported. Importing the GUI
pulls in CustomTkinter and Tk; asking a frozen bundle for its version number
should not cost that.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.localise import it_count, it_date, it_number
from core.predictor import METHODS
from core.version import APP_NAME, APP_TITLE, __version__


def _parse_args():
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=APP_TITLE,
        epilog="Senza argomenti apre l'interfaccia.",
    )
    parser.add_argument("--version", "-V", action="store_true", help="stampa la versione ed esce")
    parser.add_argument(
        "--check", action="store_true",
        help="esegue i test di indipendenza sull'archivio e esce",
    )
    parser.add_argument(
        "--validate", type=int, metavar="N", default=None,
        help="backtest walk-forward sulle ultime N estrazioni (solo baseline) e esce",
    )
    parser.add_argument(
        "--power", type=int, metavar="N", nargs="?", const=300, default=None,
        help=(
            "calibra la validazione su vantaggi noti (N estrazioni per prova, "
            "300 se omesso) e esce"
        ),
    )
    parser.add_argument(
        "--update", action="store_true",
        help="aggiorna l'archivio dalle sorgenti configurate e esce",
    )
    parser.add_argument(
        "--import", dest="import_path", metavar="FILE", default=None,
        help="importa estrazioni da un file scaricato a mano, e esce",
    )
    parser.add_argument(
        "--forecast", nargs="?", const="frequenza", metavar="METODO", default=None,
        help=(
            "stampa una serie di numeri ed esce "
            f"({', '.join(METHODS)}; predefinito frequenza)"
        ),
    )
    parser.add_argument(
        "--self-check", action="store_true",
        help="verifica che il pacchetto compilato avvii Tk ed esegua l'analisi, poi esce",
    )
    parser.add_argument(
        "--self-check-report", metavar="FILE", default=None,
        help="scrive qui anche il rapporto di autodiagnosi; una build windowed non ha stdout",
    )
    parser.add_argument(
        "--export-sqlite", metavar="FILE", default=None,
        help="scrive l'archivio in un file SQLite interrogabile, e esce",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="scrive il risultato di --update o --import invece di limitarsi a mostrarlo",
    )
    args, unknown = parser.parse_known_args()
    if unknown:
        parser.error(f"argomenti non riconosciuti: {' '.join(unknown)}")
    return args


# The opening of the "there is nothing to analyse" message, and a contract
# with .github/workflows/ci.yml: the workflow greps a fresh checkout's
# `--check` output for it, because an empty archive has to produce an
# explanation and exit 1 rather than a traceback or a silent success.
# tests/test_release_workflow.py fails when the two stop agreeing.
NO_ARCHIVE = "Nessun archivio in"


def _load_archive_or_explain():
    from core.archive import load_archive
    from core.data_manager import ARCHIVE_PATH

    draws = load_archive(ARCHIVE_PATH)
    if not draws:
        print(
            f"{NO_ARCHIVE} {ARCHIVE_PATH}. Apri l'interfaccia e scarica "
            "l'archivio dalla scheda Archivio, oppure usa --update --yes."
        )
    return draws


def _run_check() -> int:
    from core.randomness import run_all, summarise

    draws = _load_archive_or_explain()
    if not draws:
        return 1
    results = run_all(draws)
    for r in results:
        print(f"\n{r.name}")
        statistic = (
            f"χ² = {r.statistic:.3f}, {r.dof} gdl" if r.dof else f"z = {r.statistic:+.3f}"
        )
        print(f"  {statistic}")
        print(f"  {r.verdict}")
        if r.detail:
            print(f"  {r.detail}")
    print(f"\n{summarise(results)}")
    return 0


def _run_validation(n_draws: int) -> int:
    from core.validation import walk_forward

    draws = _load_archive_or_explain()
    if not draws:
        return 1
    from core.data_manager import load_settings

    settings = load_settings()
    report = walk_forward(
        draws, methods=["casuale", "frequenza", "ritardo"], n_draws=n_draws,
        picks=int(settings.get("prediction_size", 6)),
    )
    print(
        f"{report.draws_scored} estrazioni valutate, "
        f"dal {it_date(report.first_target.date)} "
        f"al {it_date(report.last_target.date)}\n"
    )
    for r in report.results:
        print("  " + r.summary())
    # The same run read on the whole ranking rather than the top six. It sees
    # a different class of edge — see core/power.py — so it is printed beside
    # the hit count and not instead of it.
    print("\n  Sulla graduatoria completa dei novanta numeri:")
    for r in report.results:
        print("  " + r.rank_summary())
    print(f"\n{report.verdict()}")
    return 0


def _run_power(n_draws: int) -> int:
    """Calibrate the harness against edges of a known size."""
    from core.power import calibrate, report

    draws = _load_archive_or_explain()
    if not draws:
        return 1

    def progress(message: str, _fraction: float) -> None:
        print(f"  {message}", flush=True)

    print(
        f"Calibrazione su {n_draws} estrazioni per prova. "
        "Richiede qualche decina di secondi.\n"
    )
    print(report(calibrate(draws, n_draws=n_draws, progress=progress)))
    return 0


def _apply(incoming, write: bool) -> int:
    """Report what an import would do, and do it when asked.

    Shared by --update and --import so the two cannot drift into disagreeing
    about when it is safe to write.
    """
    from core.archive import load_archive, merge_draws, preview_merge, save_archive
    from core.data_manager import ARCHIVE_PATH

    existing = load_archive(ARCHIVE_PATH)
    preview = preview_merge(existing, incoming)
    print(f"\n{preview.describe()}")
    for issue in preview.new_issues:
        print(f"  [{issue.severity}] {issue.message}")
    for line in preview.conflicts[:10]:
        print(f"  conflitto: {line}")

    if not preview.added and not preview.updated:
        return 0
    if not write:
        print("\nProva a vuoto — non è stato scritto nulla. Usa --yes per applicare.")
        return 0
    if not preview.safe:
        print(
            "\nScrittura rifiutata: questo import contraddice estrazioni già "
            "registrate o introdurrebbe errori di integrità. Esaminalo dalla scheda "
            "Archivio, che lo mostra riga per riga."
        )
        return 1

    merged, added, updated = merge_draws(existing, incoming)
    save_archive(ARCHIVE_PATH, merged)
    print(
        f"\nScritto: {added} aggiunte, {updated} aggiornate, "
        f"{it_number(len(merged))} in archivio."
    )
    return 0


def _run_update(write: bool) -> int:
    """Try each source in order of trust, and report what each one did.

    estrazioni.it publishes the whole archive as one CSV and is the best
    source known; when it answers, nothing else needs to run. The bulk mirror
    is the zero-configuration bootstrap for an empty archive, and the scrape
    is the last resort. A failure of any of them is reported rather than
    fatal: on any given day it is entirely normal for one to work and the
    others not to.
    """
    from datetime import date

    from core.archive import load_archive
    from core.data_manager import ARCHIVE_PATH, load_settings
    from core.sources import (
        BulkArchiveSource,
        EstrazioniItSource,
        HtmlTableSource,
        SourceError,
    )

    settings = load_settings()
    existing = load_archive(ARCHIVE_PATH)
    incoming = []

    def report(message, fraction=0.0):
        print(f"  {message}")

    print("Scarico l'esportazione completa da estrazioni.it.")
    try:
        incoming += EstrazioniItSource().fetch(report)
    except SourceError as exc:
        print(f"  estrazioni.it non ha risposto: {exc}")
    else:
        # That export runs from 1997 to the last draw, so nothing else has
        # anything to add and there is no reason to bother four other hosts.
        return _apply(incoming, write)

    if not existing:
        print("Nessun archivio — parto dal mirror storico.")
        try:
            incoming += BulkArchiveSource(
                settings["bulk_archive_url"],
                repair_labels=bool(settings.get("auto_repair_labels", True)),
            ).fetch(report)
        except SourceError as exc:
            print(f"  mirror storico non disponibile: {exc}")

    # The year to scrape from is the last one *anything* covers, including the
    # bootstrap that just ran and has not been written yet. Reading it from
    # `existing` alone would scrape only the current year on a fresh install
    # and leave everything between 2020 and now to a second invocation.
    known = existing + incoming
    last_year = max(d.year for d in known) if known else 1997
    years = list(range(last_year, date.today().year + 1))
    print(f"Scansione delle pagine {years[0]}–{years[-1]}.")
    try:
        incoming += HtmlTableSource(settings["html_archive_url"], years).fetch(report)
    except SourceError as exc:
        print(f"  scansione fallita: {exc}")

    if not incoming:
        print(
            "\nNessuna sorgente ha prodotto dati. Scarica il file a mano e usa "
            "--import."
        )
        return 1
    return _apply(incoming, write)


def _run_import(path: str, write: bool) -> int:
    from core.sources import LocalFileSource, SourceError

    try:
        incoming = LocalFileSource(path).fetch(lambda m, f=0.0: print(f"  {m}"))
    except SourceError as exc:
        print(f"Import fallito: {exc}")
        return 1
    return _apply(incoming, write)


def _run_forecast(method: str) -> int:
    """One prediction, printed. Also the end-to-end check on the model.

    ``--forecast timesfm`` is the only code path that downloads the checkpoint
    and runs a real forward pass, which makes it the thing CI runs on demand:
    everything else about the forecaster is exercised by tests that stop short
    of the 1.3 GB of weights.
    """
    from core.data_manager import load_settings
    from core.predictor import predict, value_note

    draws = _load_archive_or_explain()
    if not draws:
        return 1
    settings = load_settings()

    forecaster = None
    if method == "timesfm":
        from core.forecaster import TimesFMForecaster

        forecaster = TimesFMForecaster(
            checkpoint=settings["timesfm_checkpoint"],
            device=settings["timesfm_device"],
            context_length=int(settings["context_length"]),
            representation=settings["representation"],
            window=int(settings["frequency_window"]),
            hf_token=settings.get("hf_token", ""),
        )
        print(forecaster.describe())
        if not forecaster.load_model():
            print(
                "\nTimesFM non si è caricato. Installalo con "
                "`pip install timesfm[torch]`."
            )
            return 1

    prediction = predict(
        draws, method=method, combinations=int(settings["combinations"]),
        size=int(settings.get("prediction_size", 6)),
        superstar=bool(settings.get("predict_superstar", False)),
        forecaster=forecaster, window=int(settings["frequency_window"]),
    )
    print(f"\n{prediction.method} — {prediction.note}")
    last = prediction.archive_last_date
    print(
        f"archivio: {it_number(prediction.archive_size)} estrazioni fino al "
        f"{it_date(last)}\n"
    )
    for i, combination in enumerate(prediction.combinations, 1):
        print(f"  {i}. " + "  ".join(f"{n:2d}" for n in combination))
    if prediction.size > 6:
        from core.predictor import system_columns, system_top_prize_odds

        print(
            f"\nsistema da {prediction.size} numeri: {it_number(system_columns(prediction.size))} "
            f"colonne, 1 su {it_number(system_top_prize_odds(prediction.size))} per il 6 — "
            f"e altrettante volte il costo di una giocata singola."
        )
    if prediction.superstar is not None:
        print(f"\nSuperStar: {prediction.superstar} (1 su 90, sempre)")

    from core.predictor import ticket_cost

    cost = ticket_cost(
        prediction.combinations,
        superstar=prediction.superstar is not None,
        column_price=float(settings.get("column_price", 1.0)),
        superstar_price=float(settings.get("superstar_price", 0.5)),
    )
    print(
        f"\ncosto: {it_number(cost.total, 2)} euro "
        f"({it_count(cost.columns_paid, 'colonna', 'colonne')}"
        + (f", di cui {it_number(cost.duplicated)} pagate due volte"
           if cost.duplicated else "")
        + ")"
    )
    spread = prediction.scores[prediction.ranked[0]] - prediction.scores[prediction.ranked[-1]]
    print(f"\nescursione dei punteggi sui novanta numeri: {spread:.6f}")
    print(f"\n{value_note()}")
    return 0


def main() -> int:
    args = _parse_args()
    if args.version:
        # Not argparse's own "version" action: that writes to sys.stdout
        # unconditionally, and a windowed build on Windows may not have one.
        # print() is a no-op when sys.stdout is None, so the exit code stays 0.
        print(f"{APP_NAME} {__version__}")
        return 0
    if args.self_check:
        from core import selfcheck

        return selfcheck.run(args.self_check_report)
    if args.check:
        return _run_check()
    if args.validate is not None:
        return _run_validation(args.validate)
    if args.power is not None:
        return _run_power(args.power)
    if args.update:
        return _run_update(args.yes)
    if args.import_path:
        return _run_import(args.import_path, args.yes)
    if args.export_sqlite:
        from core.export import export_sqlite

        draws = _load_archive_or_explain()
        if not draws:
            return 1
        path = export_sqlite(draws, args.export_sqlite)
        print(f"{it_number(len(draws))} estrazioni scritte in {path}")
        print(
            "Tabelle: draws, picks (una riga per numero per estrazione), "
            "number_stats."
        )
        return 0
    if args.forecast:
        if args.forecast not in METHODS:
            print(
                f"metodo sconosciuto {args.forecast!r}; sono validi "
                f"{', '.join(METHODS)}"
            )
            return 2
        return _run_forecast(args.forecast)

    from gui.app import TycheApp

    TycheApp().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
