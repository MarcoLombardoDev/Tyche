# Tyche

**SuperEnalotto archive analysis and TimesFM 3.0 forecasting.**

A desktop application that downloads the full SuperEnalotto draw history from
December 1997, tests it for exploitable structure, hands it to Google's
TimesFM 3.0 time-series foundation model, and measures — honestly — what the
resulting predictions are worth.

The short version of that measurement: **nothing**. The draws are independent,
the tests say so, and every method in the program scores 0.4 hits out of six,
which is exactly chance. Tyche is built to demonstrate that carefully rather
than to assert it.

---

## What it does

| Tab | What it is for |
|---|---|
| **Reality check** | Five hypothesis tests of the claim that the archive is independent uniform draws. This is the first tab because it is the finding. |
| **Archive** | Download, scrape or import the draw history, and see what is wrong with it. |
| **Statistics** | Frequency, gap (*ritardo*), band and pair tables — each with the value chance would produce, in the same row. |
| **Predict** | Six numbers, from TimesFM 3.0 or from three baselines including a random one. |
| **Validate** | Walk-forward backtest of every method against the last *N* draws. |
| **Settings** | Checkpoint, device, context length, source URLs. |

There is also a command line for the two parts worth scripting:

```
python main.py --version
python main.py --check          # the five independence tests
python main.py --validate 500   # walk-forward backtest, baselines only
```

---

## Install

```
pip install torch --index-url https://download.pytorch.org/whl/cpu   # optional but smaller
pip install -r requirements.txt
python main.py
```

On Debian or Ubuntu, `tkinter` is a separate OS package and must match the
interpreter you run Tyche with:

```
sudo apt install python3-tk
```

The first TimesFM forecast downloads roughly 1.3 GB of weights from Hugging
Face. Everything except the Predict tab's TimesFM option works without them.

---

## Where the data comes from

Three sources, none of which is both current and verified:

- **Bulk archive** — one request, the whole history. It is the only source
  that has been run end to end, and it stops in **January 2020**; the mirror
  is not maintained. It bootstraps an archive, it cannot keep one.
- **Per-year scrape** — the source that would keep the archive current, and
  the one that has **never been run against the live site**, because every
  Italian lottery host was unreachable from the environment it was written
  in. It parses positionally rather than by CSS class, so it is structurally
  robust and completely untested. Check what it imports.
- **Manual import** — any CSV, TXT or TSV you downloaded yourself. Tyche
  sniffs its own format, the bulk twelve-column format, and any file with a
  date and six numbers per line. This one cannot break.

The Archive tab shows an **integrity report** next to the draw list, because
the bulk mirror is wrong in a way no per-row check can see: the first nine
draws of 1999 are labelled 1998, which gives nine duplicated contest numbers
and two pairs of different draws sharing a date. Tyche detects and repairs
that on import, from evidence rather than a hardcoded list — see
`core/archive.py::repair_year_offset`.

---

## What the tests actually found

Run against the bulk archive: **3,076 draws, 3 December 1997 to 21 January 2020**.

| Test | Result |
|---|---|
| Uniformity of the 90 numbers | χ² = 96.9 on 89 dof, p = 0.27 — no bias |
| Gap (*ritardo*) distribution | χ² = 50.5 on 50 dof, p = 0.45 — gaps are geometric, nothing is ever "due" |
| Serial independence, draw t → t+1 | χ² = 0.16, p = 0.69 — the last draw tells you nothing |
| Repeats between consecutive draws | χ² = 1.21 on 3 dof, p = 0.75 — mean overlap 0.396 against 0.400 expected |
| Sum of the six numbers | z = +4.20, **p = 0.00003** — see below |

Four of five are exactly what a fair game produces. The fifth is not, and it
is the one honest finding in this repository:

> **The mean sum of the six numbers is 277.7 against an expected 273.0.** The
> effect is small (about +0.8 per number, a tilt of under 2%), stable across
> every sub-period tested, and shows as a +0.41 correlation between a number
> and how often it has been drawn — numbers 46–90 come up about 5% more often
> than 1–45.

Before treating that as real: it was measured on **one unverified mirror**,
which is already known to be wrong about nine of its rows, and it has not been
checked against the official archive. It is more likely to be an artefact of
that file than a property of the game. And even taken at face value it is
worthless to a player: a 5% tilt does not begin to close a gap where the prize
fund is a fixed minority share of the stakes.

The walk-forward backtest is the part that settles the practical question.
Over the last 800 draws, six picks each:

| Method | Hits per draw | Against chance | p |
|---|---|---|---|
| random | 0.3700 | −24.0 | 0.15 |
| frequency ("hot") | 0.3987 | −1.0 | 0.95 |
| gap (*ritardo*) | 0.3975 | −2.0 | 0.91 |

Chance is 0.4000. Nothing beats it, including the 330-million-parameter model.

---

## Odds, which no method changes

Exact combinatorics on a 90-number wheel, six drawn:

| Category | One in |
|---|---|
| 6 | 622,614,630 |
| 5+1 | 103,769,105 |
| 5 | 1,250,230 |
| 4 | 11,907 |
| 3 | 327 |

These hold whatever numbers are played. Prizes are pari-mutuel — a share of
the stakes rather than a fixed payout — so the operator keeps a fixed cut and
the expected return on a line is below its price, always.

---

## How TimesFM is used

`core/features.py` turns the archive into a `(90, T)` matrix: one series per
number, one column per draw. `core/forecaster.py` hands all ninety to TimesFM
3.0 and asks for the next value of each.

Two details that are easy to get wrong:

- **It uses `TimesFM3Evaluator`, not `TimesFM3Forecaster`.** The model attends
  over at most 32 variates per forward pass. The Evaluator is the subclass
  that chunks a wider input and reassembles it, so ninety numbers become three
  groups of thirty-two. It is *not* one joint context over all ninety, and
  anyone repeating the "TimesFM 3.0 is multivariate so it models them all
  together" line should know that.
- **The series it is fed matters.** The raw 0/1 presence series has a mean of
  6/90 and no gradient; the rolling-frequency series is smooth enough to
  forecast and invents momentum that is not there, because a moving average of
  white noise looks like a trend. Tyche defaults to frequency and offers
  presence, which forecasts to a flat line — worth seeing once.

---

## Licensing

Tyche is a **private project**, all rights reserved. See `LICENSE`.

The TimesFM split matters if that ever changes: the `timesfm` package code is
Apache-2.0, but the `google/timesfm-3.0-pytorch` **weights** are under
`timesfm-non-commercial-license-v1.0` and are restricted to non-commercial,
non-production use. Weights up to 2.5 remain Apache-2.0 — but 2.5 has no
native multivariate forecasting and is not a drop-in replacement for what
`core/forecaster.py` does.

---

## Running the tests

```
python -m pytest tests/ -q                                    # core only
TYCHE_REQUIRE_GUI=1 xvfb-run -a python -m pytest tests/ -q     # everything
```

The GUI suite skips itself when there is no display or no tkinter, and a run
reporting "58 passed, 1 skipped" means the entire interface went untested.
`TYCHE_REQUIRE_GUI=1` turns that skip into a failure; set it whenever you
intend to have verified a GUI change.

---

*Tyche is named for the Greek goddess of chance. She is not on anyone's side.*
