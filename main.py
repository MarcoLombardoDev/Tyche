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
    python main.py --check          # the five independence tests
    python main.py --validate 500   # walk-forward backtest, baselines only

``--version`` is handled before ``gui.app`` is imported. Importing the GUI
pulls in CustomTkinter and Tk; asking a frozen bundle for its version number
should not cost that.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

    from gui.app import TycheApp

    TycheApp().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
