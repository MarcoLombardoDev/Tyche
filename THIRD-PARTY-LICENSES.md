# Third-party licences

Tyche is AGPL-3.0-or-later. This file records what it depends on, under which
licence, and what each of those licences asks of anyone who redistributes a
copy — because the AGPL obliges Tyche to pass its own terms on, and says
nothing about anybody else's.

The versions below are the ones installed in the environment these notes were
written in. A frozen Windows build carries whatever `requirements.txt`
resolved to on the day it was built, which need not be the same; check the
build if it matters to you.

## What Tyche requires to run

| Component | Version | Licence | What it asks of you |
|---|---|---|---|
| Python, standard library | 3.12 | PSF-2.0 | Attribution. Nothing further. |
| customtkinter | 6.0.0 | CC0-1.0 | Nothing. Dedicated to the public domain. |
| numpy | 2.5.2 | BSD-3-Clause (with 0BSD, MIT, Zlib and CC0 parts) | Reproduce the notice and the disclaimer. |
| requests | 2.34.2 | Apache-2.0 | Reproduce the notice; keep any NOTICE file. |
| timesfm | ≥3.0 | Apache-2.0 | Reproduce the notice. **The weights are separate — see below.** |
| torch | (pulled in by timesfm) | BSD-3-Clause | Reproduce the notice and the disclaimer. |

Pulled in by the above rather than asked for directly: `certifi` (MPL-2.0),
`charset-normalizer` (MIT), `idna` (BSD-3-Clause), `urllib3` (MIT),
`darkdetect` (BSD-3-Clause), `packaging` (Apache-2.0).

**None of these is copyleft in a way that reaches Tyche's own code.** MPL-2.0,
which `certifi` carries, is file-level weak copyleft: it governs `certifi`'s
own files and nothing else. Nothing here requires Tyche to be AGPL — that is a
choice, not an obligation inherited from a dependency.

## The model weights are not the model code

This is the distinction that matters most in this file, and it is easy to miss
because the two arrive together.

- The **`timesfm` package** is Apache-2.0. It is code, and it is permissively
  licensed.
- The **weights** Tyche downloads at runtime are a separate work under a
  separate licence. `google/timesfm-3.0-pytorch`, which Tyche uses by default,
  declares **`timesfm-non-commercial-license-v1.0`**: non-commercial,
  non-production use only.

Checked against the model cards on 6 September 2026, by the
`checkpoint-licence` job in `.github/workflows/ci.yml`, which anyone can
re-run:

| Checkpoint | Declared licence |
|---|---|
| `google/timesfm-3.0-pytorch` | `other` → `timesfm-non-commercial-license-v1.0` |
| `google/timesfm-2.5-200m-pytorch` | `apache-2.0` |
| `google/timesfm-1.0-200m-pytorch` | `apache-2.0` |

None of the three is gated: the weights download without anyone accepting
anything, which is exactly how a restriction like this goes unnoticed.

**What this means for you.** The AGPL lets you use Tyche for any purpose,
including commercially. That permission is Tyche's to give and it is given.
It does not extend to the TimesFM 3.0 weights, which are not Tyche's to
license: running the `timesfm` method commercially would need the 2.5
checkpoint, which is Apache-2.0 and which the checkpoint setting already
accepts — though `core/forecaster.py` is written against the 3.0 API and would
need work to drive it.

Every other method in the program — `frequenza`, `ritardo`, `casuale` — and
the whole archive, statistics, independence-testing and validation machinery
runs without downloading any weights at all.

Tyche never redistributes the weights. It downloads them on the user's own
machine, from Hugging Face, on first use.

## The draw data

Historical draw results are facts, not creative works, and facts are not
copyrightable. The *compilations* Tyche downloads are another matter: each
source publishes its archive under its own terms, and those terms govern
redistributing a copy of that archive. They do not reach the numbers
themselves.

Tyche ships no archive. `data/` is git-ignored and every file in it was
fetched by whoever ran the program.

## Reproducing this

```
python - <<'PY'
import importlib.metadata as m
for pkg in ("customtkinter", "numpy", "requests", "timesfm"):
    md = m.metadata(pkg)
    print(pkg, m.version(pkg), md.get("License-Expression") or md.get("License"))
PY
```

and, for the checkpoints, dispatch the `CI` workflow and read the
`checkpoint-licence` job.
