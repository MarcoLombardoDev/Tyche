**Tyche — SuperEnalotto archive analysis and TimesFM 3.0 forecasting.**

A desktop application that downloads the complete SuperEnalotto draw history
from December 1997, tests it for exploitable structure, hands it to Google's
TimesFM 3.0 time-series foundation model, and measures honestly what the
resulting predictions are worth.

The short version of that measurement: **nothing**. The draws are independent,
the tests say so, and every method in the program scores 0.4 hits out of six —
which is exactly chance. Tyche is built to demonstrate that carefully rather
than to assert it, which is why the random baseline sits in the same menu as
the 330M-parameter model, at the same size.

⚠️ **This program cannot help you win.** It has no predictive power and makes
no claim to any. The odds it prints are exact and unchangeable: 1 in
622,614,630 for six numbers, 1 in 327 for three. Prizes are pari-mutuel, so
the operator keeps a fixed share of every euro staked and the expected return
on a line is below its price whatever is played.

## Running it from source

A Windows build is attached below; on anything else, run it from source.

```
git clone https://github.com/MarcoLombardoDev/Tyche.git
cd Tyche
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python main.py
```

On Debian or Ubuntu, `tkinter` is a separate OS package and must match the
interpreter you run Tyche with: `sudo apt install python3-tk`.

The first TimesFM forecast downloads about 1.3 GB of weights from Hugging
Face. Everything else — the archive, the independence tests, the statistics,
the baselines and the whole validation harness — works without them.

There is a command line for the parts worth scripting:

```
python main.py --update --yes        # refresh the archive
python main.py --check               # the five independence tests
python main.py --validate 500        # walk-forward backtest
python main.py --forecast timesfm    # six numbers
python main.py --export-sqlite data/tyche.db
```

## What was verified before this was published

On the tagged commit, before the release was created:

- `ruff check .` across the repository;
- the whole test suite with `TYCHE_REQUIRE_GUI=1` under Xvfb, so the
  interface is genuinely exercised rather than skipped;
- a check that the version the program reports matches the tag on this page.

And on the Windows build, before it was attached:

- it starts Tk for real and comes up on the `win32` backend, builds the
  feature matrices, runs the five independence tests and round-trips an
  archive through its own persistence code — that is `--self-check`, and
  `--version` alone would prove none of it;
- TimesFM is genuinely inside the bundle, not silently dropped;
- the launcher starts the program, and refuses to when the recorded digest
  does not match.

## Licence

Private, all rights reserved. The `timesfm` package is Apache-2.0; the
`google/timesfm-3.0-pytorch` **weights** it downloads are under
`timesfm-non-commercial-license-v1.0` and are restricted to non-commercial,
non-production use.
