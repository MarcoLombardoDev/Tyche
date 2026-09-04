# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
docs/generate_screenshots.py — Tyche

Regenerates the README screenshots. They are committed files and they go stale
silently, so run this after any change to the interface:

    SHOTDIR=docs/screenshots xvfb-run -a python docs/generate_screenshots.py

Every panel is filled with real output before it is captured — the tests are
run, a prediction is generated, a short backtest is scored — because a
screenshot of an empty panel documents the layout and nothing else.

The prediction shot deliberately uses the *ritardo* baseline rather than
TimesFM. The weights are 1.3 GB and are not present on a machine that is only
building documentation, and a screenshot showing a baseline is truer to the
product's argument anyway: the balls look exactly as confident either way.

The capture is Pillow's ImageGrab against the X display, cropped to the
window's own bounds so the black Xvfb desktop does not end up in the file.
Pillow is a documentation dependency and is deliberately absent from
requirements.txt — running Tyche never needs it.
"""

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from PIL import ImageGrab  # noqa: E402

import core.data_manager as dm  # noqa: E402
from core.archive import Draw, load_archive, save_archive  # noqa: E402

OUT = Path(os.environ.get("SHOTDIR", REPO_ROOT / "docs" / "screenshots"))
DISPLAY = os.environ.get("DISPLAY", ":0")
OUT.mkdir(parents=True, exist_ok=True)


def _archive():
    """The real archive if one is on disk, otherwise a synthetic stand-in.

    Screenshots built from a synthetic archive would show a fair game that is
    fair by construction, which is not evidence of anything. The real one is
    preferred and the fallback exists so this script runs on a clean checkout.
    """
    draws = load_archive(dm.ARCHIVE_PATH)
    if draws:
        print(f"using the real archive: {len(draws):,} draws")
        return draws
    import random
    from datetime import date, timedelta

    print("no archive on disk — generating a synthetic one for the screenshots")
    rng = random.Random(0)
    synthetic = []
    day = date(2005, 1, 1)
    for i in range(2000):
        picked = rng.sample(range(1, 91), 7)
        synthetic.append(Draw(date=day, contest=i + 1, numbers=tuple(picked[:6]),
                              jolly=picked[6], year=2005, source="synthetic"))
        day += timedelta(days=2)
    save_archive(dm.ARCHIVE_PATH, synthetic)
    return synthetic


_archive()

from gui.app import TycheApp  # noqa: E402
from gui.prediction_panel import _METHOD_LABELS  # noqa: E402

app = TycheApp()
app.geometry("1280x840")
app.update()

# Fill the panels that are empty until something is run.
app._panels["reality"].run_tests()
prediction = app._panels["prediction"]
prediction.method.set(_METHOD_LABELS["ritardo"])
prediction._generate()
validation = app._panels["validation"]
validation.n_draws.delete(0, "end")
validation.n_draws.insert(0, "400")
validation._run()
for _ in range(200):                      # let the validation worker finish
    app.update()
    if validation.verdict.cget("text"):
        break
    time.sleep(0.05)
app.update()

SHOTS = [
    ("reality", "01_prova_del_nove"),
    ("archive", "02_archivio"),
    ("statistics", "03_statistiche"),
    ("prediction", "04_previsione"),
    ("validation", "05_validazione"),
    ("settings", "06_impostazioni"),
]
state = {"i": 0}


def step():
    if state["i"] >= len(SHOTS):
        app.destroy()
        return
    view, filename = SHOTS[state["i"]]
    state["i"] += 1
    app.show(view)
    app.update_idletasks()
    app.update()

    def grab(name=filename):
        try:
            x0, y0 = app.winfo_rootx(), app.winfo_rooty()
            box = (x0, y0, x0 + app.winfo_width(), y0 + app.winfo_height())
            image = ImageGrab.grab(xdisplay=DISPLAY, bbox=box)
            image.save(OUT / f"{name}.png")
            print("shot", name, image.size)
        except Exception as exc:
            print("shot FAILED", name, exc)
        app.after(200, step)

    app.after(500, grab)


app.after(800, step)
app.mainloop()
print("done ->", OUT)
