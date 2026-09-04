# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
tests/test_gui_smoke.py — Tyche

Builds the real window, switches through every panel and runs the buttons.
It catches the whole class of failure the headless tests cannot: a typo in a
widget option, a panel that raises on an empty archive, a callback wired to a
method that no longer exists.

**A skipped GUI suite is not a passing one.** These tests skip themselves when
there is no display or no tkinter, and a run that reports "58 passed, 12
skipped" looks exactly like a healthy one at a glance. Argus has this problem
and its own notes warn about it. Here, setting

    TYCHE_REQUIRE_GUI=1

turns every skip in this file into a failure, which is what CI and any session
that claims to have verified a GUI change should set. The default stays a skip
so that ``pytest tests/`` on a machine without Tk still runs the core suite.

Running them:

    xvfb-run -a python -m pytest tests/ -q                 # Linux, headless
    TYCHE_REQUIRE_GUI=1 xvfb-run -a python -m pytest tests/ -q

tkinter is an OS package and must match the interpreter running the tests: a
``python3-tk`` built for 3.12 does nothing for a 3.11 interpreter, and the
import error looks identical to not having installed it at all.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REQUIRE_GUI = os.environ.get("TYCHE_REQUIRE_GUI", "").strip() not in ("", "0", "false")


def _unavailable(reason: str):
    """Skip, or fail if the run has declared that the GUI must be tested."""
    if REQUIRE_GUI:
        pytest.fail(f"TYCHE_REQUIRE_GUI is set but the GUI cannot run: {reason}")
    pytest.skip(reason, allow_module_level=True)


try:
    import tkinter  # noqa: F401
except ImportError as exc:
    _unavailable(f"tkinter is not importable ({exc})")

if importlib.util.find_spec("customtkinter") is None:
    _unavailable("customtkinter is not installed")

if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
    _unavailable("no DISPLAY; run under xvfb-run")

from core.archive import Draw, save_archive  # noqa: E402


def _sample_archive(n: int = 600):
    import random
    from datetime import date, timedelta

    rng = random.Random(4)
    draws = []
    for i in range(n):
        picked = rng.sample(range(1, 91), 7)
        draws.append(Draw(
            date=date(2005, 1, 1) + timedelta(days=3 * i),
            contest=i + 1, numbers=tuple(picked[:6]), jolly=picked[6], year=2005,
        ))
    return draws


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A real window backed by a temporary archive and settings file.

    Everything is redirected into ``tmp_path`` before the app is constructed,
    so a test run never reads or writes the developer's own archive — and a
    test that saves settings does not silently reconfigure their install.
    """
    import core.data_manager as dm

    archive = tmp_path / "superenalotto.csv"
    save_archive(archive, _sample_archive())
    monkeypatch.setattr(dm, "ARCHIVE_PATH", archive)
    monkeypatch.setattr(dm, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(dm, "PREDICTION_LOG_PATH", tmp_path / "log.jsonl")

    import gui.app as gui_app

    monkeypatch.setattr(gui_app, "ARCHIVE_PATH", archive)

    try:
        window = gui_app.TycheApp()
    except tkinter.TclError as exc:
        _unavailable(f"Tk could not open a window ({exc})")
    window.update()
    yield window
    window.destroy()


def test_window_opens_with_every_panel(app):
    from gui.app import VIEWS

    assert len(app._panels) == len(VIEWS)
    assert app.draws, "the fixture archive should have loaded"


def test_every_panel_can_be_shown_and_refreshed(app):
    from gui.app import VIEWS

    for key, _, _ in VIEWS:
        app.show(key)
        app.update()
        assert app._active == key


def test_panels_survive_an_empty_archive(app):
    """First run: no archive on disk. Every panel must still render."""
    from gui.app import VIEWS

    app.set_draws([])
    for key, _, _ in VIEWS:
        app.show(key)
        app.update()


def test_reality_check_runs_and_reaches_a_verdict(app):
    app.show("reality")
    app._panels["reality"].run_tests()
    app.update()
    assert app._panels["reality"].verdict.cget("text")


def test_each_baseline_method_produces_combinations(app):
    from gui.prediction_panel import _METHOD_LABELS

    panel = app._panels["prediction"]
    app.show("prediction")
    for method in ("frequency", "gap", "random"):
        panel.method.set(_METHOD_LABELS[method])
        panel._generate()
        app.update()
        assert panel._prediction is not None
        assert panel._prediction.method == method
        assert len(panel._prediction.combinations) >= 1


def test_timesfm_without_the_model_reports_instead_of_crashing(app):
    """The failure has to reach the status bar, not the worker's traceback."""
    import time

    from core.forecaster import TimesFMForecaster
    from gui.prediction_panel import _METHOD_LABELS

    if TimesFMForecaster().load_model(lambda *_: None):
        pytest.skip("timesfm is installed in this environment")

    panel = app._panels["prediction"]
    app.show("prediction")
    panel.method.set(_METHOD_LABELS["timesfm"])
    panel._generate()
    for _ in range(60):
        app.update()
        if "fail" in app._status.cget("text").lower():
            break
        time.sleep(0.05)
    assert app._status.cget("text")


def test_validation_runs_the_baselines_to_a_verdict(app):
    import time

    panel = app._panels["validation"]
    app.show("validation")
    panel.n_draws.delete(0, "end")
    panel.n_draws.insert(0, "120")
    panel._run()
    for _ in range(120):
        app.update()
        if panel.verdict.cget("text"):
            break
        time.sleep(0.05)
    assert "hits per draw" in panel.verdict.cget("text")


def test_validation_rejects_a_non_numeric_draw_count(app):
    panel = app._panels["validation"]
    app.show("validation")
    panel.n_draws.delete(0, "end")
    panel.n_draws.insert(0, "many")
    panel._run()
    app.update()
    assert "whole number" in app._status.cget("text")


def test_settings_save_round_trips_and_keeps_integer_types(app):
    import core.data_manager as dm

    panel = app._panels["settings"]
    app.show("settings")
    panel._widgets["context_length"].delete(0, "end")
    panel._widgets["context_length"].insert(0, "512")
    panel._save()
    app.update()
    assert dm.load_settings()["context_length"] == 512
    assert isinstance(dm.load_settings()["context_length"], int)


def test_settings_rejects_a_non_numeric_integer_field(app):
    panel = app._panels["settings"]
    app.show("settings")
    panel._widgets["context_length"].delete(0, "end")
    panel._widgets["context_length"].insert(0, "lots")
    panel._save()
    app.update()
    assert "not a whole number" in app._status.cget("text")


def test_one_worker_at_a_time(app):
    """Two concurrent archive writes would lose one of them silently."""
    app._busy = True
    app.run_worker("second job", lambda report: None, lambda result: None)
    assert "already running" in app._status.cget("text")
    app._busy = False


def test_a_failing_worker_reports_the_real_error(app):
    """Regression: the lambda used to close over the `except ... as exc` name,
    which Python deletes at the end of the block, so the status bar showed a
    NameError about a free variable instead of the actual failure."""
    import time

    def boom(report):
        raise RuntimeError("the archive caught fire")

    app.run_worker("doomed", boom, lambda result: None)
    for _ in range(40):
        app.update()
        if "caught fire" in app._status.cget("text"):
            break
        time.sleep(0.05)
    assert "the archive caught fire" in app._status.cget("text")


def test_archive_panel_shows_how_far_behind_the_archive_is(app):
    """The fixture archive ends in 2005 and today is not 2005."""
    app.show("archive")
    app.update()
    text = app._panels["archive"].freshness.cget("text")
    assert "missing" in text or "Current as of" in text


def test_footer_marks_a_stale_archive(app):
    assert "behind" in app._archive_label.cget("text")


def test_a_clean_import_does_not_stop_to_ask(app, monkeypatch):
    """A dialog that always says 'everything is fine' is one nobody reads."""
    from tkinter import messagebox

    from core.archive import Draw

    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a) or True)

    last = max(d.date for d in app.draws)
    fresh = Draw(date=last.replace(year=last.year + 1), contest=999,
                 numbers=(2, 4, 6, 8, 10, 12), jolly=14)
    before = len(app.draws)
    app._panels["archive"]._merge_result([fresh])
    app.update()
    assert asked == []
    assert len(app.draws) == before + 1


def test_a_contradicting_import_asks_first_and_declining_writes_nothing(app, monkeypatch):
    from tkinter import messagebox

    from core.archive import Draw

    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    stored = app.draws[10]
    bad = Draw(date=stored.date, contest=stored.contest,
               numbers=(81, 82, 83, 84, 85, 86), jolly=1, year=stored.year)
    before = [d.to_row() for d in app.draws]
    app._panels["archive"]._merge_result([bad])
    app.update()
    assert [d.to_row() for d in app.draws] == before
    assert "cancelled" in app._status.cget("text")


def test_the_scraper_always_asks_even_when_the_preview_is_clean(app, monkeypatch):
    """It is the source that has never been checked against a real page."""
    from tkinter import messagebox

    from core.archive import Draw

    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a) or True)
    last = max(d.date for d in app.draws)
    fresh = Draw(date=last.replace(year=last.year + 2), contest=998,
                 numbers=(3, 5, 7, 9, 11, 13), jolly=15)
    app._panels["archive"]._merge_result([fresh], always_confirm=True)
    app.update()
    assert len(asked) == 1


def test_the_self_check_passes_and_writes_its_report(tmp_path):
    """What the release workflow runs against the Windows bundle.

    Not using the `app` fixture: --self-check starts its own Tk root, and the
    point is to exercise exactly the path the frozen build takes.
    """
    from core.selfcheck import run

    report = tmp_path / "self-check.txt"
    assert run(str(report)) == 0
    text = report.read_text(encoding="utf-8")
    assert "self-check: PASSED" in text
    # The workflow greps for this line to confirm the bundle came up on the
    # platform's real toolkit rather than a fallback.
    assert "windowing system:" in text
