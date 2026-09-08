# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
model_store.py — Tyche

Whether TimesFM can run, and fetching the weights when it cannot yet.

Before this module the answer arrived as a failure: pressing «Esegui» with no
checkpoint on disk started a worker, waited, and put a stack-trace tail in the
status bar. A 1.3 GB download is not an error condition — it is a thing the
user has to be told about and offered — so the state is now something the
interface can ask for *before* anything is started.

**Nothing here imports torch or timesfm.** :func:`availability` answers from
``importlib.util.find_spec`` and the Hugging Face cache, so a panel can call
it while drawing itself. Importing the model to find out whether the model is
importable costs several seconds and, the first time, a gigabyte.

**The token is not required for the default checkpoint, and saying otherwise
would be a lie the interface tells.** The `checkpoint-licence` CI job asked
the three model cards directly: none of them is gated, so the weights download
with nothing configured. A token is needed only for a repository whose owner
restricted access, which is why the download failure path mentions it and the
ready path does not.

**What the percentage is a percentage of.** huggingface_hub reports a download
as one progress bar per file plus an outer bar counting files, all created as
the workers reach them — so there is no single bar to read, and no total known
up front. :class:`DownloadProgress` adds the byte bars together, and the
message it composes always prints the denominator beside the percentage. That
matters: when a new file's bar appears the total grows and the percentage can
fall, and a reader who can see ``546 MB di 1,29 GB`` understands why, where a
bare ``42%`` that becomes ``31%`` looks like a bug.
"""

from __future__ import annotations

import importlib.util
import pathlib
import time
from dataclasses import dataclass

from core.localise import it_bytes
from core.version import DEFAULT_TIMESFM_CHECKPOINT

# The states :func:`availability` can report. Values are Italian because they
# are shown; the constants are what code compares against.
READY = "pronto"
NO_PACKAGE = "pacchetto assente"
NO_CHECKPOINT = "pesi assenti"
UNKNOWN = "non verificabile"


@dataclass(frozen=True)
class Availability:
    """Whether a forecast could start right now, and what to do if not."""

    state: str
    detail: str
    can_download: bool

    @property
    def ready(self) -> bool:
        return self.state == READY

    @property
    def usable(self) -> bool:
        """Whether the interface should let the user choose TimesFM.

        ``UNKNOWN`` counts as usable. It means the check itself could not run —
        timesfm is installed but huggingface_hub is not importable, which
        happens with an unusual install — and refusing to offer a method
        because Tyche could not verify it would be worse than letting the
        attempt report its own failure.
        """
        return self.state in (READY, UNKNOWN)


def _has_module(name: str) -> bool:
    """Whether ``name`` is importable, without importing it.

    A seam: the tests set this to describe a machine other than the one they
    are running on, which is the only way to exercise the missing-package
    branch on a machine where the package is present, and the reverse.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# What a snapshot has to contain before Tyche will call it usable. Any one of
# them: the format depends on the checkpoint and on which loader wrote it.
#
# No ``.msgpack``: that is Flax, and it was here until a test noticed that the
# same suffix sat in SKIPPABLE. Counting a format the download deliberately
# skips as evidence that the download worked is the kind of contradiction that
# ends in a cache the program calls ready forever and cannot load.
_WEIGHT_SUFFIXES = (".safetensors", ".bin", ".pt", ".pth", ".ckpt")


def _checkpoint_cached(checkpoint: str) -> bool:
    """Whether usable weights are already in the Hugging Face cache.

    ``local_files_only`` makes ``snapshot_download`` a cache query: it returns
    a path without touching the network. Asking the cache directory ourselves
    would mean hard-coding the ``models--org--name/snapshots`` layout, which is
    huggingface_hub's to change.

    **And then the snapshot is checked for weights**, which the query alone
    does not do. Offline it can only compare against the file list it already
    has, so an interrupted download that left a config and a tokeniser behind
    resolves happily — and the path panel then says "pronto" over a model that
    cannot load. That is exactly the state a user reported: ready on one
    screen, "non si è caricato" on the next.
    """
    from huggingface_hub import snapshot_download

    try:
        path = snapshot_download(repo_id=checkpoint, local_files_only=True)
    except Exception:  # noqa: BLE001 — every miss is "not cached"
        return False
    return any(
        item.suffix in _WEIGHT_SUFFIXES
        for item in pathlib.Path(path).rglob("*")
        if item.is_file()
    )


def availability(checkpoint: str = DEFAULT_TIMESFM_CHECKPOINT) -> Availability:
    """What stands between the user and a TimesFM forecast."""
    if not _has_module("timesfm3"):
        return Availability(
            NO_PACKAGE,
            "TimesFM non è installato in questa copia di Tyche. Gli altri tre "
            "metodi funzionano lo stesso — e ottengono lo stesso punteggio.",
            can_download=False,
        )
    if not _has_module("huggingface_hub"):
        return Availability(
            UNKNOWN,
            "Non riesco a verificare se i pesi sono già scaricati: "
            "huggingface_hub non è importabile. Puoi provare lo stesso.",
            can_download=False,
        )
    if _checkpoint_cached(checkpoint):
        return Availability(
            READY,
            f"TimesFM è pronto: i pesi di {checkpoint} sono già su questo "
            "computer e l'esecuzione è tutta locale.",
            can_download=False,
        )
    # How much is already there, so a download that stopped part-way says so
    # rather than reading as "nothing has happened". The owner pressed the
    # button several times against a cache holding 882 MB of 1.23 GB and had
    # no way to know that from this screen.
    return Availability(NO_CHECKPOINT, _missing_detail(checkpoint), can_download=True)


def _missing_detail(checkpoint: str) -> str:
    """What to say when the weights are not usable yet."""
    partial = 0
    expected = 0
    try:
        partial = _downloaded_bytes(str(repo_cache_dir(checkpoint)))
        _, expected = expected_download(checkpoint)
    except Exception:  # noqa: BLE001 — a detail line must not raise
        pass
    if partial and expected and partial < expected:
        return (
            f"Il download di {checkpoint} si è fermato a {it_bytes(partial)} di "
            f"{it_bytes(expected)}. Ripremere «Scarica il modello» riprende da "
            "lì: quello che è arrivato resta nella cache."
        )
    return (
        f"I pesi di {checkpoint} non sono ancora su questo computer: circa "
        "1,3 GB da scaricare una volta sola. Il checkpoint predefinito è ad "
        "accesso libero, quindi non serve alcun token."
    )


class DiskProgress:
    """Reports a download by measuring the cache, not by trusting a library.

    **The first version hooked huggingface_hub's tqdm and it produced nothing.**
    ``tqdm_class`` was a documented parameter, the arithmetic on top of it was
    unit-tested, and on the owner's Windows machine the status bar sat on
    "TimesFM…" for the whole download and never moved. Whether hf_hub honours
    that hook was a claim about somebody else's library that no test here
    could check — and it was wrong, or at least not true of that version.

    Bytes on disk are not a claim about anybody's library. This walks the
    repository's own cache folder and reports what is actually there, which
    also means a resumed download opens at 72% instead of 0% — because that is
    where it is.

    ``measure`` is the seam: the tests hand it a directory they built.
    """

    def __init__(
        self,
        path,
        expected: int = 0,
        report=None,
        throttle: float = 0.5,
        clock=time.monotonic,
        measure=None,
    ):
        self._path = pathlib.Path(path)
        self._expected = int(expected or 0)
        self._report = report
        self._throttle = throttle
        self._clock = clock
        self._measure = measure or self._on_disk
        self._last_emit = -1e9
        self._last_percent = -1
        self.downloaded = 0

    def _on_disk(self) -> int:
        """Bytes under the folder, ignoring what cannot be read.

        A file can vanish between the walk and the stat — hf_hub renames an
        ``.incomplete`` blob into place as it finishes — and a progress
        indicator that raises on that has failed at the one job it has.
        """
        total = 0
        try:
            for item in self._path.rglob("*"):
                try:
                    if item.is_file():
                        total += item.stat().st_size
                except OSError:
                    continue
        except OSError:
            return self.downloaded
        return total

    @property
    def fraction(self) -> float:
        return min(self.downloaded / self._expected, 1.0) if self._expected else 0.0

    def message(self) -> str:
        if self._expected:
            return (
                f"scaricati {it_bytes(self.downloaded)} di "
                f"{it_bytes(self._expected)} ({self.fraction:.0%})"
            )
        return f"scaricati {it_bytes(self.downloaded)}"

    def sample(self, force: bool = False) -> bool:
        """Measure, and report if enough has changed. True when it reported."""
        self.downloaded = self._measure()
        if self._report is None:
            return False
        percent = int(self.fraction * 100)
        now = self._clock()
        if (
            not force
            and percent == self._last_percent
            and now - self._last_emit < self._throttle
        ):
            return False
        self._last_percent = percent
        self._last_emit = now
        self._report(self.message(), self.fraction)
        return True


def repo_cache_dir(checkpoint: str):
    """Where huggingface_hub keeps one repository, or the whole cache.

    The ``models--org--name`` layout is hf_hub's to change, which is why
    :func:`_checkpoint_cached` asks the library instead of reading it. Here it
    is only used to point a byte counter at the right folder, and the fallback
    when it is not there is the cache root — a progress bar that counts
    slightly too much is a great deal better than none, which is what the
    previous version delivered.
    """
    from huggingface_hub import constants

    root = pathlib.Path(constants.HF_HUB_CACHE)
    folder = root / ("models--" + checkpoint.replace("/", "--"))
    return folder if folder.exists() else root


def expected_download(checkpoint: str, token: str = "", ignore=()) -> tuple[int, int]:
    """``(files, bytes)`` the Hub says this checkpoint is, or ``(0, 0)``.

    Asked before the download so the percentage has a denominator that does
    not move. The previous version added up the per-file progress bars as they
    appeared, so its total grew during the download and the percentage could
    fall — honest, and confusing.
    """
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(checkpoint, files_metadata=True, token=token or None)
        wanted = [
            s for s in (getattr(info, "siblings", None) or [])
            if not any(s.rfilename.endswith(p.lstrip("*")) for p in ignore)
        ]
        return len(wanted), sum(s.size or 0 for s in wanted)
    except Exception:  # noqa: BLE001 — a missing denominator is not a failure
        return 0, 0


def download_failure_message(checkpoint: str, error: str) -> str:
    """What to tell the user when the download did not happen.

    The token is mentioned on an authorisation failure and *only* then. Naming
    it every time would teach the reader that TimesFM needs a Hugging Face
    account, which the default checkpoint does not — and a user who then goes
    and makes one has been sent on an errand by their own software.
    """
    lowered = error.lower()
    if any(k in lowered for k in ("401", "403", "gated", "authoriz", "autoriz", "restricted")):
        return (
            f"Hugging Face ha rifiutato l'accesso a {checkpoint}: "
            "il repository è ad accesso ristretto. Accetta le condizioni sulla "
            "sua pagina e incolla un token in Impostazioni → Token Hugging Face. "
            f"({error})"
        )
    return (
        f"Download di {checkpoint} non riuscito: {error}. "
        "Se la rete è a posto, riprova: quello che era già stato scaricato "
        "resta nella cache e non viene ripreso da capo."
    )


# Formats a PyTorch loader can never use. The repository carries the same
# weights several ways so that every framework finds its own, and fetching all
# of them is how "1,3 GB" turns into a great deal more than 1,3 GB.
#
# Chosen as an exclusion rather than an allow-list on purpose: an allow-list
# that misses one file the loader wants produces a download that looks
# complete and fails on the first forecast, which is the worst of the
# available failures. Excluding formats no torch build reads cannot do that.
# Formats a PyTorch loader can never use. A model repository often carries
# the same weights several ways so that every framework finds its own, and
# fetching all of them is how "1.3 GB" turns into a great deal more.
#
# **On Tyche's own checkpoint this list matches nothing**, which the owner
# noticed: the repository is five files — one 1.23 GB safetensors and four
# small ones — so the exclusion changes neither the count nor the size. It
# stays because the setting lets somebody point Tyche at a checkpoint that is
# not this one, and it costs nothing when there is nothing to skip.
#
# An exclusion rather than an allow-list on purpose: a list that misses one
# file the loader wants produces a download that looks complete and fails on
# the first forecast.
SKIPPABLE = (
    "*.h5",             # TensorFlow
    "*.msgpack",        # Flax
    "*.onnx",
    "*.onnx_data",
    "*.tflite",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.pdf",
)

# How many times a truncated download is resumed before giving up.
# huggingface_hub continues from what is on disk, so an attempt that stopped
# at 72% costs the remaining 28% and not the lot.
DOWNLOAD_ATTEMPTS = 3

# How complete counts as complete. Not 1.0: the Hub's own sizes and what
# lands on disk can differ by metadata, and a check that demands the last byte
# would call a working download broken.
COMPLETE_ENOUGH = 0.995


def download_checkpoint(
    checkpoint: str = DEFAULT_TIMESFM_CHECKPOINT,
    token: str = "",
    progress=None,
    slim: bool = True,
    attempts: int = DOWNLOAD_ATTEMPTS,
) -> str:
    """Fetch the weights, reporting progress, and check that they all arrived.

    **The check is the point of this function.** The owner's download stopped
    at 882 MB of 1.23 GB, several times, and nothing said so: the call
    returned, the panel moved on, and the next screen reported the weights
    missing with no hint that 72% of them were sitting in the cache. A
    truncated download is the normal failure of a gigabyte over a domestic
    connection, so it is handled rather than merely survived — measured
    against what the Hub says the repository weighs, and resumed.
    """
    ignore = SKIPPABLE if slim else ()
    files, expected = expected_download(checkpoint, token, ignore)
    if expected:
        _report(
            progress,
            f"{files} file, {it_bytes(expected)} da scaricare da huggingface.co…",
        )
    else:
        # No denominator: the Hub did not answer. The download can still work,
        # and saying "connecting" beats saying nothing while it tries.
        _report(progress, "contatto huggingface.co…")

    path = ""
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            _report(
                progress,
                f"download incompleto, riprendo (tentativo {attempt} di {attempts})…",
            )
        path = _snapshot(checkpoint, token, progress, ignore, expected)
        if not expected or _downloaded_bytes(path) >= expected * COMPLETE_ENOUGH:
            break
    else:
        got = _downloaded_bytes(path)
        raise RuntimeError(
            f"Il download si è interrotto a {it_bytes(got)} di "
            f"{it_bytes(expected)} dopo {attempts} tentativi. Quello che è "
            "arrivato resta nella cache, quindi ripremere il pulsante riprende "
            "da lì invece di ricominciare."
        )

    if slim and not _has_weights(path):
        _report(progress, "nessun file di pesi nella selezione: riscarico tutto.")
        path = _snapshot(checkpoint, token, progress, (), 0)
    return path


def _snapshot(checkpoint: str, token: str, progress, ignore, expected: int) -> str:
    """One attempt, with a thread counting the bytes as they land."""
    import threading

    from huggingface_hub import snapshot_download

    tracker = DiskProgress(repo_cache_dir(checkpoint), expected, progress)
    done = threading.Event()

    def watch():
        while not done.wait(0.5):
            tracker.sample()

    watcher = threading.Thread(target=watch, daemon=True, name="download-progress")
    watcher.start()
    try:
        path = snapshot_download(
            repo_id=checkpoint,
            token=token or None,
            ignore_patterns=list(ignore) or None,
        )
    except Exception as exc:  # noqa: BLE001 — every failure becomes a sentence
        raise RuntimeError(download_failure_message(checkpoint, str(exc))) from exc
    finally:
        done.set()
        watcher.join(timeout=2)
    tracker.sample(force=True)
    return str(path)


def _downloaded_bytes(path: str) -> int:
    """What is in the snapshot, for comparing against what was promised."""
    total = 0
    for item in pathlib.Path(path).rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _has_weights(path: str) -> bool:
    """Whether a downloaded snapshot holds anything a loader could open."""
    return any(
        item.suffix in _WEIGHT_SUFFIXES
        for item in pathlib.Path(path).rglob("*")
        if item.is_file()
    )


def _report(progress, message: str, fraction: float = 0.0) -> None:
    if progress is not None:
        progress(message, fraction)


def diagnose(checkpoint: str = DEFAULT_TIMESFM_CHECKPOINT, token: str = "") -> list[str]:
    """Everything that decides whether TimesFM can run, as printable lines.

    Written for the case this module was not built for: the user says the
    download does not work and neither of us knows why. ``availability`` gives
    one word; this gives the interpreter, the two packages and their versions,
    where the cache is, what is in it, how much room the disk has, and what
    the Hub says when asked — each one a thing that has actually broken a
    download somewhere.

    Never raises. A diagnostic that dies on the first missing import diagnoses
    nothing, and the machine it runs on is by definition the odd one.
    """
    import platform
    import shutil
    import sys

    lines = [
        f"Tyche su Python {sys.version.split()[0]}, {platform.platform()}",
        f"checkpoint richiesto: {checkpoint}",
        f"token configurato: {'sì' if token else 'no'} "
        "(non serve per il checkpoint predefinito)",
        "",
    ]

    for name in ("timesfm3", "huggingface_hub", "torch"):
        try:
            module = __import__(name)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{name:<16} NON importabile — {type(exc).__name__}: {exc}")
        else:
            version = getattr(module, "__version__", "versione ignota")
            lines.append(f"{name:<16} {version}")

    lines.append("")
    try:
        from huggingface_hub import constants

        cache = pathlib.Path(constants.HF_HUB_CACHE)
        lines.append(f"cache: {cache}")
        lines.append(f"       esiste: {'sì' if cache.exists() else 'no'}")
        if cache.exists():
            files = [f for f in cache.rglob("*") if f.is_file()]
            size = sum(f.stat().st_size for f in files)
            lines.append(
                f"       {len(files)} file, {it_bytes(size)} in totale"
            )
            weights = [f for f in files if f.suffix in _WEIGHT_SUFFIXES]
            lines.append(f"       di cui {len(weights)} file di pesi")
            for item in sorted(weights, key=lambda f: -f.stat().st_size)[:5]:
                lines.append(f"         {it_bytes(item.stat().st_size):>10}  {item.name}")
        usage = shutil.disk_usage(cache.parent if cache.exists() else pathlib.Path.home())
        lines.append(f"       spazio libero sul disco: {it_bytes(usage.free)}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"cache non ispezionabile — {type(exc).__name__}: {exc}")

    lines.append("")
    state = availability(checkpoint)
    lines.append(f"stato: {state.state} — {state.detail}")

    lines.append("")
    lines.append("Interrogo l'Hub (serve rete):")
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(checkpoint, files_metadata=True, token=token or None)
        siblings = list(getattr(info, "siblings", []) or [])
        total = sum(s.size or 0 for s in siblings)
        lines.append(f"  raggiunto. {len(siblings)} file, {it_bytes(total)} in totale.")
        lines.append(f"  accesso ristretto (gated): {getattr(info, 'gated', 'ignoto')}")
        skipped = [
            s for s in siblings
            if any(s.rfilename.endswith(p.lstrip('*')) for p in SKIPPABLE)
        ]
        if skipped:
            saved = sum(s.size or 0 for s in skipped)
            lines.append(
                f"  di cui {len(skipped)} in formati che Tyche non scarica "
                f"({it_bytes(saved)} risparmiati)."
            )
        for item in sorted(siblings, key=lambda s: -(s.size or 0))[:10]:
            lines.append(f"    {it_bytes(item.size or 0):>10}  {item.rfilename}")

        # The comparison that says "truncated" rather than leaving two
        # numbers on the page for a reader to subtract.
        on_disk = _downloaded_bytes(str(repo_cache_dir(checkpoint)))
        if total and on_disk < total * COMPLETE_ENOUGH:
            lines += [
                "",
                f"  INCOMPLETO: sul disco ci sono {it_bytes(on_disk)} dei "
                f"{it_bytes(total)} attesi ({on_disk / total:.0%}). "
                "Il download si è interrotto; ripremere il pulsante riprende.",
            ]
        elif total:
            lines.append(f"  completo: {it_bytes(on_disk)} sul disco.")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  non raggiunto — {type(exc).__name__}: {exc}")

    return lines


def ensure_checkpoint(
    checkpoint: str = DEFAULT_TIMESFM_CHECKPOINT,
    token: str = "",
    progress=None,
) -> None:
    """Download the weights if they are not cached, otherwise do nothing.

    Called by :meth:`core.forecaster.TimesFMForecaster.load_model` so that the
    percentage appears whether the user pressed «Scarica il modello» or went
    straight to «Esegui». Silent when huggingface_hub is not importable: the
    loader is then left to do whatever it does, which is what happened before
    this module existed.
    """
    if not _has_module("huggingface_hub"):
        return
    if _checkpoint_cached(checkpoint):
        return
    download_checkpoint(checkpoint, token=token, progress=progress)
