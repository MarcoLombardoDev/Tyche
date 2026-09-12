# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

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
import time
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


def _generate(app, count: str = "1"):
    """Press Genera and pump the loop until the worker's result lands.

    The four methods run off-thread now — TimesFM has to, and running three of
    them inline and one in a worker would be two code paths — so a single
    ``update()`` is not enough to see the answer.
    """
    import time

    panel = app._panels["prediction"]
    app.show("prediction")
    panel.count.set(count)
    panel._generate()
    # Four seconds was the budget and it was not enough: the whole file went
    # red once on this line while another suite had the machine, and passed
    # alone straight afterwards. A worker thread's share of a loaded runner is
    # not something the test can control, so the budget is generous — twelve
    # seconds — rather than tight. It still fails, and fast, when nothing is
    # coming: the loop ends the moment a prediction lands.
    for _ in range(600):
        app.update()
        if panel._predictions:
            return panel
        time.sleep(0.02)
    raise AssertionError(
        "no prediction after waiting: "
        f"status={app._status.cget('text')!r} busy={app._busy} "
        f"queued={app._queue.qsize()} "
        # Which of the two it was matters: still busy means the worker is
        # genuinely slow, while not-busy with a full queue means the result
        # arrived and the main loop never drained it.
    )


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


def test_every_method_runs_at_once_and_gets_its_own_quarter(app):
    """No selector: the four run together, and the control is one of them.

    Choosing a method meant seeing one, which turned four measurements into a
    preference. Side by side, a reader can watch 330 million parameters and a
    random number generator disagree about which six numbers to play.
    """
    from core.predictor import method_name

    panel = _generate(app)

    # TimesFM needs weights this machine does not have; the other three are
    # unconditional and each must have filled its own cell.
    for method in ("frequenza", "ritardo", "casuale"):
        assert method in panel._predictions, method
        prediction = panel._predictions[method]
        assert prediction.method == method
        assert len(prediction.combinations) == 1
        assert panel._cells[method].balls.winfo_children(), (
            f"{method} produced nothing to look at"
        )
    # The scores moved out of the cells and into the report beside them.
    report = panel.report.get("1.0", "end")
    for method in ("frequenza", "ritardo", "casuale"):
        assert method_name(method) in report


def test_the_random_control_keeps_its_quarter_of_the_screen(app):
    """The guard the panel's whole argument rests on.

    A change that quietly drops the random baseline — or shrinks it, or moves
    it out of the grid — takes the demonstration with it and leaves four
    methods that all look like attempts.
    """
    from core.predictor import METHODS

    panel = app._panels["prediction"]
    app.show("prediction")
    app.update()
    assert set(panel._cells) == set(METHODS)
    assert "casuale" in panel._cells
    widths = {m: cell.winfo_width() for m, cell in panel._cells.items()}
    assert len(set(widths.values())) == 1, f"the cells are not the same size: {widths}"
    for method, cell in panel._cells.items():
        assert cell.winfo_ismapped(), f"{method} is built but not on the screen"


def test_timesfm_without_the_model_says_so_in_its_own_cell(app):
    """The other three still have something to say, so only one cell is lost."""
    from core.forecaster import TimesFMForecaster

    if TimesFMForecaster().load_model(lambda *_: None):
        pytest.skip("timesfm is installed in this environment")

    panel = _generate(app)
    assert "timesfm" not in panel._predictions
    assert panel._cells["timesfm"].state.cget("text").strip()
    assert panel._predictions, "a missing model must not cost the other three"


def _force_availability(monkeypatch, state):
    """Describe a machine other than this one to both screens.

    Both modules bind ``availability`` into their own namespace with a
    ``from`` import, so patching one leaves the other reading the real
    machine — which is how these two tests first passed on the strip and
    failed on the path.
    """
    import gui.home_panel as home_panel
    import gui.model_status as model_status

    for module in (model_status, home_panel):
        monkeypatch.setattr(module, "availability", lambda *args, **kwargs: state)


def test_a_missing_model_is_stated_before_it_is_offered(app, monkeypatch):
    """The defect this replaces: press Genera, wait, get a generic failure.

    A 1.3 GB download that has not happened is not an error condition. It is a
    fact about the machine, knowable before anything is started, so the panel
    says it. It does not offer the button: step 2 of the path has one, and two
    buttons for one download is two places to look.
    """
    from core.model_store import NO_CHECKPOINT, Availability

    _force_availability(
        monkeypatch,
        Availability(NO_CHECKPOINT, "I pesi non sono su questo computer.", True),
    )
    panel = app._panels["prediction"]
    app.show("prediction")
    app.update()
    said = panel.model_status.label.cget("text")
    assert "pesi" in said
    assert "Percorso" in said, "an error here has to say where it can be fixed"
    assert not panel.model_status.button.winfo_ismapped(), (
        "the download belongs to the path, not to this panel"
    )


def test_the_path_offers_the_download_as_its_second_step(app, monkeypatch):
    """Step 2 acts rather than navigating: the download belongs to no tab."""
    from core.model_store import NO_CHECKPOINT, Availability

    _force_availability(
        monkeypatch,
        Availability(NO_CHECKPOINT, "I pesi non sono su questo computer.", True),
    )
    home = app._panels["home"]
    app.show("home")
    app.update()
    assert "pesi" in home._states()["model"][0]
    assert home._states()["model"][2] == "!"
    assert home._buttons["model"].cget("state") == "normal"

    called = {}
    monkeypatch.setattr(
        app, "download_model", lambda on_done=None: called.setdefault("yes", True)
    )
    home._act("model")
    assert called, "step 2 did not start the download"


def test_the_download_button_is_absent_when_there_is_nothing_to_download(app, monkeypatch):
    """A missing *package* is not fixed by fetching weights."""
    from core.model_store import NO_PACKAGE, Availability

    _force_availability(
        monkeypatch, Availability(NO_PACKAGE, "TimesFM non è installato.", False)
    )
    app.show("prediction")
    app.update()
    assert not app._panels["prediction"].model_status.button.winfo_ismapped()

    home = app._panels["home"]
    app.show("home")
    app.update()
    assert home._buttons["model"].cget("state") == "disabled"


def test_ready_weights_are_reported_on_both_screens(app, monkeypatch):
    """Availability is read on every tab switch, not once at start-up.

    The download can be started from the path, so the Prediction tab has to
    notice that it happened.
    """
    from core.model_store import READY, Availability

    _force_availability(monkeypatch, Availability(READY, "TimesFM è pronto.", False))

    app.show("prediction")
    app.update()
    # Beside «Genera» a ready model says nothing at all: the strip there is
    # for problems, and the path panel is where the state is reported.
    assert app._panels["prediction"].model_status.label.cget("text") == ""

    home = app._panels["home"]
    app.show("home")
    app.update()
    assert home._states()["model"][2] == "✓"


def test_the_method_is_written_TimesFM_where_the_user_reads_it(app):
    """`timesfm` is an identifier settings.json stores, not a label to show."""
    from core.predictor import METHOD_NAMES

    panel = app._panels["prediction"]
    app.show("prediction")
    app.update()
    shown = {
        method: cell.winfo_children()[0].winfo_children()[0].cget("text")
        for method, cell in panel._cells.items()
    }
    assert shown["timesfm"] == "TimesFM"
    assert shown["frequenza"] == "Frequenza"
    assert set(shown.values()) == set(METHOD_NAMES.values())


def test_the_status_bar_and_the_licence_line_are_on_every_tab(app):
    """They were packed after the body, which expands — so pack clipped them.

    The symptom was tab-dependent and therefore easy to miss: they showed on
    the short panels and vanished on Archivio and Previsione, which are the
    two whose content is tallest.
    """
    from gui.app import VIEWS

    for key, _, _ in VIEWS:
        app.show(key)
        app.update()
        assert app._status.winfo_ismapped(), f"status bar missing on {key}"
        assert app._licence_label.winfo_ismapped(), f"licence line missing on {key}"
        assert app._licence_email.winfo_ismapped(), f"contact missing on {key}"


def test_the_licence_line_is_not_the_colour_of_a_hairline_rule(app):
    """It was SEP, the separator colour, and could not be read."""
    from gui.theme import SEP

    assert app._licence_label.cget("text_color") != SEP


def test_prose_wraps_to_the_window_and_not_to_a_number(app):
    """A wraplength in pixels is a guess about somebody else's screen.

    Also the regression guard for the hang: the first two attempts at this
    bound Configure on the label and read its own width, which oscillates —
    update() never returned and the whole suite stopped rather than failing.
    """
    home = app._panels["home"]
    app.show("home")
    app.update()
    app.update_idletasks()

    # Against the parent's real width rather than a threshold: whether a
    # geometry() request is granted depends on the window manager, and the
    # Windows runner does not grant it. A label that merely kept its
    # constructor value fails this on any machine, which a threshold did not.
    for label in home._state_labels.values():
        parent = label.master.winfo_width()
        assert parent > 200, "the panel never got a width; nothing to check"
        assert abs(label.cget("wraplength") - (parent - 32)) < 8, (
            f"wraplength {label.cget('wraplength')} against a parent of {parent}"
        )


def test_the_archive_tab_carries_the_figures_that_had_their_own_tab(app):
    """Statistics folded into Archivio in 0.11.0; the tab is gone."""
    from gui.app import VIEWS

    assert "statistics" not in [key for key, *_ in VIEWS]
    panel = app._panels["archive"]
    app.show("archive")
    app.update()
    assert panel.summary.cget("text").strip()
    assert "uscite" in panel.freq_box.get("1.0", "end")
    assert "decina" in panel.decade_box.get("1.0", "end")
    assert "coppia" in panel.pairs_box.get("1.0", "end")


def test_the_archive_tab_offers_one_source_and_a_file(app):
    """The mirror and the scraper were traps beside a button that works."""
    panel = app._panels["archive"]
    app.show("archive")
    app.update()
    assert not hasattr(panel, "_fetch_bulk")
    assert not hasattr(panel, "_fetch_html")
    assert not hasattr(panel, "debug_html")
    assert hasattr(panel, "_fetch_export") and hasattr(panel, "_import_file")


def test_the_method_cells_are_bordered_and_hold_only_the_numbers(app):
    """Four cells on one dark background read as one page of text.

    And since 1.0.7 they hold the answer and nothing else: the scores moved to
    the report beside them, because six numbers in a fifth of a cell with the
    arithmetic filling the rest is the wrong way round.
    """
    from gui.theme import ACCENT

    panel = app._panels["prediction"]
    for cell in panel._cells.values():
        assert cell.cget("border_width") >= 1
        assert cell.cget("border_color") == ACCENT
        assert not hasattr(cell, "box"), "the scores are back inside the cell"


def test_every_label_is_one_size_unless_it_is_a_heading(app):
    """One body size for everything a user reads, and one exception.

    A CTkLabel with no ``font=`` silently takes CustomTkinter's default, so
    before 1.0.0 the same screen carried 11, 12, 13 and the toolkit's own —
    four kinds of text saying the same kind of thing. Headings are exempt
    because they are bold, which is the thing that makes them headings; the
    buttons size themselves and are not labels.
    """
    import customtkinter as ctk

    from gui.app import VIEWS
    from gui.widgets import BODY_SIZE

    wrong = []

    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, ctk.CTkLabel) and child.cget("text").strip():
                # Empty ones are CTkScrollableFrame's own title widget, which
                # displays nothing and whose size therefore cannot be wrong.
                font = child.cget("font")
                size, weight = font.cget("size"), font.cget("weight")
                if weight != "bold" and size != BODY_SIZE:
                    wrong.append((child.cget("text")[:40], size))
            walk(child)

    for key, _, _ in VIEWS:
        app.show(key)
        app.update()
    walk(app)
    assert not wrong, f"labels off the body size: {wrong}"


def test_the_window_carries_the_application_icon(app):
    """Argus shipped none for a while and ran under the bare Tk feather.

    The PhotoImage is kept on the instance because Tk holds only a weak
    reference to it: dropping it leaves a blank icon and nothing raises.
    """
    assert getattr(app, "_app_icon", None) is not None
    assert app._app_icon.width() > 0


def test_the_icon_files_are_committed():
    """Drawn once and committed, so no build depends on which fonts a runner has."""
    assets = Path(__file__).resolve().parent.parent / "assets"
    for name in ("app_icon.png", "app_icon.ico", "app_icon.icns"):
        assert (assets / name).is_file(), name


def test_the_app_opens_on_the_path(app):
    """A user who opens Tyche must land on the map, not on a panel.

    The complaint this whole panel answers was that the sections had no
    visible order; opening on any one of them is what produced that.
    """
    assert app._active == "home"


def test_the_path_lists_the_three_conditions_in_order():
    """Archive, model, prediction — the two things that must be true, then go."""
    from gui.home_panel import STEPS

    assert [key for key, *_ in STEPS] == ["archive", "model", "prediction"]


def test_every_navigating_step_opens_a_panel_that_exists(app):
    """A step pointing at a missing panel would fail only when clicked.

    Step 2 is the exception and deliberately so: it downloads rather than
    navigating, because the weights belong to no tab.
    """
    from gui.home_panel import STEPS

    for key, *_ in STEPS:
        if key == "model":
            continue
        assert key in app._panels
        app.show(key)
        app.update()
        assert app._active == key


def test_the_path_tells_a_first_time_user_to_fetch_the_archive(app, monkeypatch):
    """Everything is blocked on step 1, and step 1 says so."""
    monkeypatch.setattr(app, "draws", [])
    home = app._panels["home"]
    home.refresh()
    states = home._states()
    assert "Nessun archivio" in states["archive"][0]
    assert "Serve prima l'archivio" in states["prediction"][0]


def test_the_path_reports_what_the_prediction_step_produced(app):
    """The steps carry live state, not a static checklist."""
    home = app._panels["home"]
    home.refresh()
    assert "Non ancora generate" in home._states()["prediction"][0]

    _generate(app)
    home.refresh()
    after = home._states()["prediction"]
    assert "Non ancora generate" not in after[0]
    assert "metodi a confronto" in after[0]
    assert after[2] == "✓", "the tick is what a user scans for"


def test_a_current_archive_is_marked_done(app):
    """The archive card is the one indicator that was already right."""
    home = app._panels["home"]
    home.refresh()
    text, _, mark = home._states()["archive"]
    assert "estrazioni" in text
    assert mark in ("✓", "!")


def test_the_prediction_follows_the_system_size_and_superstar_settings(app):
    """The two settings live on another tab, so this is the wire between them.

    They apply to every one of the four tickets, which is why the shape and
    the price are stated once above the grid rather than in each cell.
    """
    app.settings["prediction_size"] = 9
    app.settings["predict_superstar"] = True
    panel = _generate(app)

    for prediction in panel._predictions.values():
        assert prediction.size == 9
        assert all(len(c) == 9 for c in prediction.combinations)
        assert prediction.superstar is not None

    text = panel.report.get("1.0", "end")
    assert "Sistema integrale da 9 numeri" in text
    assert "84 colonne" in text
    # The honest sentence has to be on the screen, not only in the source.
    assert "non di guadagnare di più" in text
    assert "SuperStar" in text


def test_a_plain_column_says_so_and_shows_no_system_table(app):
    app.settings["prediction_size"] = 6
    app.settings["predict_superstar"] = False
    panel = _generate(app)

    assert all(p.superstar is None for p in panel._predictions.values())
    text = panel.report.get("1.0", "end")
    assert "Colonna singola" in text
    assert "Sistema integrale" not in text


def test_settings_save_keeps_a_price_a_number(app):
    """Floats fell straight through to strings before 0.6.0.

    The panel knew bool and int and nothing else, so a price typed here came
    back as text and the first arithmetic on it would have been what raised.
    A comma is accepted because that is what an Italian keyboard produces.
    """
    panel = app._panels["settings"]
    app.show("settings")
    panel._widgets["column_price"].delete(0, "end")
    panel._widgets["column_price"].insert(0, "1,25")
    panel._save()
    app.update()
    assert app.settings["column_price"] == 1.25
    assert isinstance(app.settings["column_price"], float)


def test_settings_save_refuses_a_price_that_is_not_a_number(app):
    panel = app._panels["settings"]
    app.show("settings")
    app.settings["column_price"] = 1.0
    panel._widgets["column_price"].delete(0, "end")
    panel._widgets["column_price"].insert(0, "gratis")
    panel._save()
    app.update()
    assert app.settings["column_price"] == 1.0
    assert "non è un numero" in app._status.cget("text")


def test_the_prediction_prints_what_the_ticket_costs(app):
    app.settings["prediction_size"] = 9
    app.settings["predict_superstar"] = True
    app.settings["column_price"] = 1.0
    app.settings["superstar_price"] = 0.5
    # Set explicitly rather than leaning on the default, which is 1 since
    # 0.6.1 — the duplication this checks only exists with several plays.
    panel = _generate(app, count="5")

    text = panel.report.get("1.0", "end")
    assert "Costo della giocata" in text
    # Five plays of 84 columns at 1.50 each.
    assert "630,00" in text
    assert "pagate due volte" in text


def test_the_cost_is_for_one_ticket_and_not_for_four(app):
    """Four methods on screen is four alternatives, not a stake to multiply.

    The single most expensive thing this layout could get wrong: a reader who
    reads one price under four tickets and assumes it is the total.
    """
    panel = _generate(app)
    text = panel.report.get("1.0", "end")
    assert "quattro" in text
    assert "non una giocata da moltiplicare" in text
    # In the same block as the price, not three screens away where the two
    # can be read apart.
    assert "Costo della giocata" in text


def test_a_single_combination_wastes_nothing_and_says_so(app):
    """The shipped default, and the reason it is the default."""
    app.settings["prediction_size"] = 9
    app.settings["predict_superstar"] = False
    panel = _generate(app, count="1")

    text = panel.report.get("1.0", "end")
    assert "pagate due volte" not in text
    assert "scelte successive" not in text


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
    assert "non è un numero intero" in app._status.cget("text")


def test_one_worker_at_a_time(app):
    """Two concurrent archive writes would lose one of them silently."""
    app._busy = True
    app.run_worker("second job", lambda report: None, lambda result: None)
    assert "già un'operazione in corso" in app._status.cget("text")
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
    assert "mancano" in text or "Aggiornato al" in text


def test_footer_marks_a_stale_archive(app):
    assert "indietro" in app._archive_label.cget("text")


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
    assert "annullato" in app._status.cget("text")


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
    assert "autodiagnosi: SUPERATA" in text
    # The workflow greps for this line to confirm the bundle came up on the
    # platform's real toolkit rather than a fallback.
    assert "sistema grafico:" in text


# ─────────────────────────────────────────────────────────────
# The licence bar
#
# Ported from Argus, which carries the same strip and the same four checks.
# The line is the one place these products deliberately read alike, wording
# included, so a test that only asserted "something mentions AGPL" would let
# them drift apart while staying green.
# ─────────────────────────────────────────────────────────────

def test_the_licence_bar_names_the_licence_and_the_address(app):
    """Whoever is running the program is the person who may have a licensing
    or security question, so the address is spelled out rather than promised
    'on request'."""
    from core.version import APP_NAME, CONTACT_EMAIL

    text = app._licence_label.cget("text")
    assert "AGPL-3.0" in text
    assert "© 2026 Marco Lombardo" in text
    assert APP_NAME in text
    assert app._licence_email.cget("text") == CONTACT_EMAIL


def test_the_licence_bar_is_in_italian_like_everything_else_a_user_reads(app):
    """The other products say "Licensed under ... | Contact:" and Tyche does
    not, deliberately.

    It forecasts an Italian lottery and exists only for people who play it, so
    the language boundary applies to this strip like to any other text a user
    reads — it was English in the first version of this bar and that was the
    wrong call. ``AGPL-3.0`` stays as it is: an SPDX identifier is not a
    phrase to translate.
    """
    text = app._licence_label.cget("text")
    assert "Distribuito con licenza AGPL-3.0" in text
    assert "Contatti:" in text
    for english in ("Licensed under", "Contact:"):
        assert english not in text, f"the bar still reads English: {english!r}"


def test_the_address_looks_clickable(app):
    """A bare label that happens to react to clicks is undiscoverable: the
    hand cursor is what says it can be clicked at all."""
    assert app._licence_email.cget("cursor") == "hand2"


def test_clicking_the_address_opens_the_mail_client(app, monkeypatch):
    from core.version import CONTACT_EMAIL
    from gui import app as app_mod

    opened = []
    monkeypatch.setattr(app_mod.webbrowser, "open", opened.append)

    app.open_contact_email()

    assert len(opened) == 1
    assert opened[0].startswith(f"mailto:{CONTACT_EMAIL}?subject=")


def test_a_missing_mail_client_does_not_crash(app, monkeypatch):
    """No mail client configured is a normal state on a headless or
    locked-down box; the address stays readable on screen, so it must not
    raise."""
    from gui import app as app_mod

    def explode(url):
        raise OSError("no mail client")

    monkeypatch.setattr(app_mod.webbrowser, "open", explode)

    app.open_contact_email()

    assert app.winfo_exists()


def test_the_weights_folder_can_be_picked_rather_than_typed(app, monkeypatch, tmp_path):
    """A Windows path typed by hand is a path with one character wrong.

    The field stays editable — ``_save`` reads the entry, not the picker — but
    the person this setting exists for has just spent an hour on a download
    that would not finish, and asking him to transcribe
    ``C:\\Users\\…\\pesi`` is asking for the next failure.
    """
    import tkinter.filedialog as filedialog

    panel = app._panels["settings"]
    entry = panel._widgets["timesfm_local_dir"]
    entry.delete(0, "end")
    entry.insert(0, "qualcosa di vecchio")

    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: str(tmp_path))
    panel._choose(entry)
    assert entry.get() == str(tmp_path)

    # Cancelling must not throw away what is already there.
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: "")
    panel._choose(entry)
    assert entry.get() == str(tmp_path)


def test_a_folder_of_weights_is_read_by_the_path_and_by_the_prediction_strip(
    app, monkeypatch, tmp_path
):
    """Both screens have to see the setting, and they read it separately.

    ``availability`` is bound into two namespaces by a ``from`` import, and
    the folder is a second argument each call site has to pass. One that
    forgot would report "pesi assenti" over a folder that works.
    """
    folder = tmp_path / "pesi"
    folder.mkdir()
    for name in ("config.json", "model.safetensors"):
        (folder / name).write_bytes(b"x" * 16)

    import gui.home_panel as home_panel
    import gui.model_status as model_status

    monkeypatch.setattr(model_status, "availability", _folder_reading_availability)
    monkeypatch.setattr(home_panel, "availability", _folder_reading_availability)
    app.settings["timesfm_local_dir"] = str(folder)

    app.show("prediction")
    app.update()
    # The strip beside «Genera» reports problems and nothing else, so a folder
    # that works shows as an empty line there and as a method that will run.
    strip = app._panels["prediction"].model_status
    assert strip.available is True, "the folder was not read by the prediction tab"
    assert strip.label.cget("text") == ""

    home = app._panels["home"]
    home.refresh()
    assert str(folder) in home._states()["model"][0]


def _folder_reading_availability(checkpoint=None, folder=""):
    """The real thing minus the package check, which this machine fails."""
    from core.model_store import NO_CHECKPOINT, READY, Availability, folder_checkpoint

    found = folder_checkpoint(folder)
    if found is None:
        return Availability(NO_CHECKPOINT, "niente pesi", True)
    return Availability(READY, f"uso i pesi nella cartella {found}.", False)


def test_every_settings_field_is_actually_on_the_screen(app):
    """Declared, reachable — and drawn. The third one was missing.

    Adding the folder picker moved ``pack`` into the branches that build each
    kind of widget, and two of them did not get one back: three option menus
    and two switches came up 1x1 and unmapped. Nothing failed. The panel
    listed every setting, ``_save`` read every setting, and a third of them
    could not be changed. The screenshot is what showed it, which is why this
    test measures pixels rather than existence.
    """
    from gui.settings_panel import FIELDS

    panel = app._panels["settings"]
    app.show("settings")
    app.update()
    for key, label, _kind, _help in FIELDS:
        widget = panel._widgets[key]
        assert widget.winfo_ismapped(), f"«{label}» is built but never packed"
        assert widget.winfo_width() > 20 and widget.winfo_height() > 10, (
            f"«{label}» is on the screen at "
            f"{widget.winfo_width()}x{widget.winfo_height()} pixels"
        )


def test_the_superstar_is_a_purple_star_with_its_number_in_it(app):
    """One widget on the numbers' own row, right-aligned, and star-shaped.

    "SuperStar" as a label cost seventy pixels the combinations wanted and a
    row of its own. A ★ character beside an ordinary purple ball replaced it
    and still said the same thing twice, in two widgets. CustomTkinter draws
    rounded rectangles and nothing else, so the badge is a Tk canvas with a
    real polygon on it — which is also what makes this test able to check the
    *shape* rather than a character somebody's font may not have.
    """
    import tkinter

    from gui.theme import ACCENT

    app.settings["predict_superstar"] = True
    panel = _generate(app)

    cell = panel._cells["frequenza"]
    first_row = cell.balls.winfo_children()[0]
    canvases = [
        child for child in first_row.winfo_children()
        if isinstance(child, tkinter.Canvas)
    ]
    assert canvases, "the SuperStar is not on the same row as the numbers"
    canvas = canvases[0]

    polygons = [i for i in canvas.find_all() if canvas.type(i) == "polygon"]
    assert len(polygons) == 1
    assert canvas.itemcget(polygons[0], "fill") == ACCENT
    # Ten vertices is not enough to prove a star — a decagon has ten too, and
    # reads as a circle. The radii have to *alternate*: five far, five near.
    # Checked by mutation, because the first version of this assertion passed
    # with every vertex pushed out to the same radius.
    import math

    coords = canvas.coords(polygons[0])
    assert len(coords) == 20
    centre = int(canvas.cget("width")) / 2
    radii = [
        math.hypot(x - centre, y - centre)
        for x, y in zip(coords[::2], coords[1::2], strict=True)
    ]
    points, notches = radii[::2], radii[1::2]
    assert min(points) > max(notches) * 1.4, (
        f"the notches are not deep enough to be a star: {radii}"
    )

    texts = [i for i in canvas.find_all() if canvas.type(i) == "text"]
    assert len(texts) == 1
    shown = canvas.itemcget(texts[0], "text")
    assert int(shown) == panel._predictions["frequenza"].superstar
    assert canvas.itemcget(texts[0], "fill") == "#ffffff"

    texts_in_cell = _all_label_texts(cell)
    assert not any("SuperStar" in t for t in texts_in_cell), (
        "the badge is there to replace that label, not to sit beside it"
    )


def test_the_button_is_dead_while_a_generation_runs(app):
    """Pressing it again during a run did nothing and said so afterwards.

    run_worker already refuses the second job, but refusing it in the status
    bar after the click is not the same as saying beforehand that the click
    will do nothing.
    """
    panel = app._panels["prediction"]
    app.show("prediction")
    app.update()
    assert panel.button.cget("state") == "normal"

    # Observed *during* the run, and that is the whole test. _generate()
    # disables the button before run_worker returns, and _enable() only
    # reaches it through the queue that update() drains — so between these two
    # lines the state is deterministic rather than a race.
    panel._generate()
    assert panel.button.cget("state") == "disabled", (
        "the button stayed live while its own job was running"
    )

    for _ in range(200):
        app.update()
        if panel._predictions:
            break
        time.sleep(0.02)
    for _ in range(50):
        app.update()
        if panel.button.cget("state") == "normal":
            break
        time.sleep(0.02)
    assert panel.button.cget("state") == "normal", (
        "the button never came back after the run"
    )

    # And it comes back even when the work raises, which is the case that
    # would otherwise leave it dead for the rest of the session.
    panel.button.configure(state="disabled")
    app.run_worker(
        "Prova",
        lambda report: (_ for _ in ()).throw(RuntimeError("boom")),
        lambda result: None,
        on_done=panel._enable,
    )
    for _ in range(200):
        app.update()
        if panel.button.cget("state") == "normal":
            break
        time.sleep(0.02)
    assert panel.button.cget("state") == "normal", (
        "a job that raised left the button disabled"
    )


def _all_label_texts(widget) -> list[str]:
    import customtkinter as ctk

    found = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkLabel):
            found.append(child.cget("text"))
        found += _all_label_texts(child)
    return found
