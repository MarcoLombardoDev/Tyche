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

from core.predictor import METHODS
from core.version import APP_NAME, APP_TITLE, __version__


def _parse_args():
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=APP_TITLE,
        epilog="Run without arguments to open the interface.",
    )
    parser.add_argument("--version", "-V", action="store_true", help="print the version and exit")
    parser.add_argument(
        "--check", action="store_true",
        help="run the independence tests on the stored archive and exit",
    )
    parser.add_argument(
        "--validate", type=int, metavar="N", default=None,
        help="walk-forward backtest over the last N draws (baselines only) and exit",
    )
    parser.add_argument(
        "--update", action="store_true",
        help="refresh the archive from the configured sources and exit",
    )
    parser.add_argument(
        "--import", dest="import_path", metavar="FILE", default=None,
        help="import draws from a file you downloaded, and exit",
    )
    parser.add_argument(
        "--forecast", nargs="?", const="frequency", metavar="METHOD", default=None,
        help=f"print one set of numbers and exit ({', '.join(METHODS)}; default frequency)",
    )
    parser.add_argument(
        "--export-sqlite", metavar="FILE", default=None,
        help="write the archive to a SQLite file for querying, and exit",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="write the result of --update or --import instead of only reporting it",
    )
    args, unknown = parser.parse_known_args()
    if unknown:
        parser.error(f"unrecognised arguments: {' '.join(unknown)}")
    return args


def _load_archive_or_explain():
    from core.archive import load_archive
    from core.data_manager import ARCHIVE_PATH

    draws = load_archive(ARCHIVE_PATH)
    if not draws:
        print(
            f"No archive at {ARCHIVE_PATH}. Open the interface and run the bulk "
            "bootstrap from the Archive tab first."
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
            f"χ² = {r.statistic:.3f}, dof {r.dof}" if r.dof else f"z = {r.statistic:+.3f}"
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
    report = walk_forward(draws, methods=["random", "frequency", "gap"], n_draws=n_draws)
    print(
        f"{report.draws_scored} draws scored, "
        f"{report.first_target.date} to {report.last_target.date}\n"
    )
    for r in report.results:
        print("  " + r.summary())
    print(f"\n{report.verdict()}")
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
        print(f"  conflict: {line}")

    if not preview.added and not preview.updated:
        return 0
    if not write:
        print("\nDry run — nothing written. Pass --yes to apply.")
        return 0
    if not preview.safe:
        print(
            "\nRefusing to write: this import contradicts stored draws or would "
            "introduce integrity errors. Review it in the Archive tab, which can "
            "show it row by row."
        )
        return 1

    merged, added, updated = merge_draws(existing, incoming)
    save_archive(ARCHIVE_PATH, merged)
    print(f"\nWritten: {added} added, {updated} updated, {len(merged):,} on record.")
    return 0


def _run_update(write: bool) -> int:
    """Bootstrap from the bulk mirror, then try the per-year scrape.

    Both are attempted and a failure of either is reported rather than fatal:
    the bulk source is reachable and dead, the scraper is live and unproven,
    and on any given day it is entirely normal for exactly one of them to
    work.
    """
    from datetime import date

    from core.archive import load_archive
    from core.data_manager import ARCHIVE_PATH, load_settings
    from core.sources import BulkArchiveSource, HtmlTableSource, SourceError

    settings = load_settings()
    existing = load_archive(ARCHIVE_PATH)
    incoming = []

    def report(message, fraction=0.0):
        print(f"  {message}")

    if not existing:
        print("No archive yet — bootstrapping from the bulk mirror.")
        try:
            incoming += BulkArchiveSource(settings["bulk_archive_url"]).fetch(report)
        except SourceError as exc:
            print(f"  bulk archive failed: {exc}")

    # The year to scrape from is the last one *anything* covers, including the
    # bootstrap that just ran and has not been written yet. Reading it from
    # `existing` alone would scrape only the current year on a fresh install
    # and leave everything between 2020 and now to a second invocation.
    known = existing + incoming
    last_year = max(d.year for d in known) if known else 1997
    years = list(range(last_year, date.today().year + 1))
    print(f"Scraping {years[0]}–{years[-1]}.")
    try:
        incoming += HtmlTableSource(settings["html_archive_url"], years).fetch(report)
    except SourceError as exc:
        print(f"  scrape failed: {exc}")

    if not incoming:
        print("\nNo source produced anything. Download a file by hand and use --import.")
        return 1
    return _apply(incoming, write)


def _run_import(path: str, write: bool) -> int:
    from core.sources import LocalFileSource, SourceError

    try:
        incoming = LocalFileSource(path).fetch(lambda m, f=0.0: print(f"  {m}"))
    except SourceError as exc:
        print(f"Import failed: {exc}")
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
            print("\nTimesFM could not be loaded. Install it with `pip install timesfm[torch]`.")
            return 1

    prediction = predict(
        draws, method=method, combinations=int(settings["combinations"]),
        forecaster=forecaster, window=int(settings["frequency_window"]),
    )
    print(f"\n{prediction.method} — {prediction.note}")
    print(f"archive: {prediction.archive_size:,} draws up to {prediction.archive_last_date}\n")
    for i, combination in enumerate(prediction.combinations, 1):
        print(f"  {i}. " + "  ".join(f"{n:2d}" for n in combination))
    spread = prediction.scores[prediction.ranked[0]] - prediction.scores[prediction.ranked[-1]]
    print(f"\nscore spread across the ninety numbers: {spread:.6f}")
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
    if args.check:
        return _run_check()
    if args.validate is not None:
        return _run_validation(args.validate)
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
        print(f"{len(draws):,} draws written to {path}")
        print("Tables: draws, picks (one row per number per draw), number_stats.")
        return 0
    if args.forecast:
        if args.forecast not in METHODS:
            print(f"unknown method {args.forecast!r}; expected one of {', '.join(METHODS)}")
            return 2
        return _run_forecast(args.forecast)

    from gui.app import TycheApp

    TycheApp().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
