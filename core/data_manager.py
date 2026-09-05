# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
data_manager.py — Tyche

Where things live on disk, and the settings file.

Every path is derived from :func:`core.paths.writable_base_dir`, never from
``Path(__file__)``. Argus learned that one the hard way: a frozen onefile
build resolves ``__file__`` into a temporary directory that is deleted on
exit, so a module computing its own base directory writes the user's data
somewhere it will not survive the session.

There is one set of defaults, in :data:`DEFAULT_SETTINGS`, and
``config/settings.template.json`` is generated from it by
``tests/test_core.py`` rather than maintained by hand. Argus keeps two
hand-written copies of its defaults and they have drifted apart at least
once — ``useExchangeBalance`` is True in the code and false in the template,
so a setting that reads as safe in the template is live in the running app.
Tyche does not get to make that mistake twice: the test fails if the template
stops matching the code.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import writable_base_dir
from core.version import DEFAULT_TIMESFM_CHECKPOINT

BASE_DIR = writable_base_dir()
DATA_DIR = BASE_DIR / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_PATH = ARCHIVE_DIR / "superenalotto.csv"
PREDICTION_LOG_PATH = DATA_DIR / "prediction_log.jsonl"
VALIDATION_DIR = DATA_DIR / "validation"
SETTINGS_PATH = BASE_DIR / "config" / "settings.json"
SETTINGS_TEMPLATE_PATH = BASE_DIR / "config" / "settings.template.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    # --- Model ---
    "timesfm_checkpoint": DEFAULT_TIMESFM_CHECKPOINT,
    "timesfm_device": "cpu",
    "hf_token": "",
    # Which of the three views in core.features the model is fed. "frequenza"
    # is the only one with enough amplitude for a forecast to have a gradient
    # to follow; "presenza" is the honest raw series and forecasts as a flat
    # line at 0.067, which is itself worth seeing once.
    "representation": "frequenza",
    "frequency_window": 150,
    # TimesFM 3.0 accepts up to 16k context. 1024 draws is about six and a
    # half years, long enough to cover any seasonality the game could have and
    # short enough to keep a CPU forecast to a few seconds.
    "context_length": 1024,

    # --- Sources ---
    "bulk_archive_url": "https://downloads.sourceforge.net/project/superenalotto/EnalStorico.CSV",
    "html_archive_url": (
        "https://www.estrazionedellotto.it/superenalotto/risultati/archivio-superenalotto-{year}"
    ),
    # Whether the bulk mirror's nine mislabelled 1999 draws are put back
    # where they belong on import. On, because they really are mislabelled
    # and the repair agrees with an independent record of the same nine.
    # Off gives the mirror's own bytes, which is how that check was made.
    "auto_repair_labels": True,

    # --- Prediction ---
    "prediction_method": "timesfm",   # "timesfm" | "frequenza" | "ritardo" | "casuale"
    "combinations": 5,

    # --- Validation ---
    # How many of the most recent draws the walk-forward backtest scores. 300
    # is about two years and takes a couple of minutes with TimesFM on a CPU;
    # the statistics module needs a few hundred before its error bars mean
    # anything.
    "validation_draws": 300,
    # Which methods the Validate tab starts with ticked, and where a run's
    # selection is remembered. TimesFM stays out of the default: one model
    # call per scored draw is not what a first click should cost.
    "validation_baselines": ["casuale", "frequenza", "ritardo"],
}


def load_settings() -> dict:
    """Read settings, filling in anything missing from :data:`DEFAULT_SETTINGS`.

    A missing or unreadable file is not an error — it is a first run, or a
    file the user broke while editing, and either way the app opens with
    defaults rather than a traceback.
    """
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy of literals
    try:
        stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return settings
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[Settings] {SETTINGS_PATH} unreadable ({exc}); using defaults")
        return settings
    if isinstance(stored, dict):
        settings.update(stored)
    return _translate_names(settings)


# 0.1.0 wrote the method and representation names in English. 0.2.0 renamed
# them, and a settings file from the older version would otherwise reach
# ``build_context`` as an unknown representation and raise where the user
# expects a forecast. Reading is where the two vocabularies meet, so this is
# the only place that has to know both.
_RENAMED = {
    "presence": "presenza",
    "frequency": "frequenza",
    "gap": "ritardo",
    "random": "casuale",
}


def _translate_names(settings: dict) -> dict:
    """Map any 0.1.0 English method or representation name to its 0.2.0 name."""
    representation = settings.get("representation")
    if isinstance(representation, str):
        settings["representation"] = _RENAMED.get(representation, representation)

    baselines = settings.get("validation_baselines")
    if isinstance(baselines, list):
        settings["validation_baselines"] = [
            _RENAMED.get(name, name) if isinstance(name, str) else name
            for name in baselines
        ]
    return settings


def save_settings(settings: dict) -> None:
    """Write settings, creating ``config/`` if needed."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SETTINGS_PATH)


def log_prediction(entry: dict) -> None:
    """Append one prediction to the log, as a line of JSON.

    JSON Lines rather than a single JSON array so that appending is one open
    in ``a`` mode and a truncated write costs the last line instead of the
    file. The log is the only way to answer "what did it say last month, and
    was it right?" after the fact, which is the question that keeps the
    validation honest — a prediction is cheap to remember and impossible to
    reconstruct.
    """
    PREDICTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(entry)
    payload.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
    with open(PREDICTION_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def load_prediction_log(limit: int | None = None) -> list[dict]:
    """Read the prediction log, newest last. Bad lines are skipped."""
    if not PREDICTION_LOG_PATH.exists():
        return []
    entries: list[dict] = []
    with open(PREDICTION_LOG_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries[-limit:] if limit else entries


def write_settings_template(path: Path | None = None) -> Path:
    """Regenerate ``config/settings.template.json`` from the live defaults.

    Called by the test suite, which then diffs the result against what is
    committed. That is the mechanism that stops the two copies drifting.
    """
    target = Path(path) if path else SETTINGS_TEMPLATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(DEFAULT_SETTINGS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target
