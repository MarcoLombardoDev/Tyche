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


def _checkpoint_cached(checkpoint: str) -> bool:
    """Whether the weights are already in the Hugging Face cache.

    ``local_files_only`` makes ``snapshot_download`` a cache query: it returns
    the path when every file is present and raises when anything is missing,
    without touching the network. Asking the cache directory ourselves would
    mean hard-coding the ``models--org--name/snapshots`` layout, which is
    huggingface_hub's to change.
    """
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(repo_id=checkpoint, local_files_only=True)
    except Exception:  # noqa: BLE001 — every miss is "not cached"
        return False
    return True


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
    return Availability(
        NO_CHECKPOINT,
        f"I pesi di {checkpoint} non sono ancora su questo computer: circa "
        "1,3 GB da scaricare una volta sola. Il checkpoint predefinito è ad "
        "accesso libero, quindi non serve alcun token.",
        can_download=True,
    )


class DownloadProgress:
    """Adds up the progress bars huggingface_hub creates during a download.

    Fed by the tqdm subclass :func:`tracking_tqdm` builds. Kept separate from
    it, and free of every huggingface_hub and tqdm import, because this is the
    part with arithmetic in it and therefore the part worth testing — on a
    machine with neither installed, which is every machine this suite runs on.

    Byte bars (``unit`` starting with ``B``) are the download. The outer bar
    counts files and has a different unit, so it supplies "3 di 5" and is kept
    out of the byte total.
    """

    def __init__(self, report=None, throttle: float = 0.5, clock=time.monotonic):
        self._report = report
        self._throttle = throttle
        self._clock = clock
        self._bytes: dict[int, list[float]] = {}      # id -> [done, total]
        self._files: list[float] = [0.0, 0.0]         # [done, total]
        self._last_emit = 0.0
        self._last_percent = -1

    # ── what the tqdm subclass calls ─────────────────────────
    def register(self, bar_id: int, total, unit: str) -> None:
        if str(unit).upper().startswith("B"):
            self._bytes[bar_id] = [0.0, float(total or 0)]
        else:
            self._files = [0.0, float(total or 0)]
        self.maybe_report()

    def advance(self, bar_id: int, amount: float) -> None:
        bar = self._bytes.get(bar_id)
        if bar is None:
            self._files[0] += float(amount or 0)
        else:
            bar[0] += float(amount or 0)
        self.maybe_report()

    def close(self, bar_id: int) -> None:
        bar = self._bytes.get(bar_id)
        # A finished file has been downloaded whole, whatever its bar last
        # said: tqdm is updated in chunks and the final one can be missed.
        if bar is not None and bar[1]:
            bar[0] = bar[1]
        self.maybe_report(force=True)

    # ── what it adds up to ───────────────────────────────────
    @property
    def downloaded(self) -> float:
        return sum(done for done, _ in self._bytes.values())

    @property
    def total(self) -> float:
        return sum(total for _, total in self._bytes.values())

    @property
    def fraction(self) -> float:
        return self.downloaded / self.total if self.total else 0.0

    def message(self) -> str:
        """The line the status bar shows. Denominator always visible."""
        if not self._bytes:
            return "Preparo il download dei pesi…"
        head = f"scarico i pesi: {it_bytes(self.downloaded)}"
        if self.total:
            head += f" di {it_bytes(self.total)} ({self.fraction:.0%})"
        files_done, files_total = self._files
        if files_total:
            head += f" — {int(files_done)} file su {int(files_total)}"
        return head

    # ── talking to the caller ────────────────────────────────
    def maybe_report(self, force: bool = False) -> bool:
        """Emit at most one line per whole percent, or per ``throttle`` seconds.

        A 1.3 GB download updates its bars thousands of times a second, and
        every call the GUI receives becomes a queued closure on the main
        thread. Unthrottled, the download makes the window unresponsive while
        reporting how well it is going.
        """
        if self._report is None:
            return False
        percent = int(self.fraction * 100)
        now = self._clock()
        if not force and percent == self._last_percent and now - self._last_emit < self._throttle:
            return False
        self._last_percent = percent
        self._last_emit = now
        self._report(self.message(), self.fraction)
        return True

    def finish(self) -> None:
        if self._report is not None:
            self._report("pesi scaricati.", 1.0)


def tracking_tqdm(tracker: DownloadProgress):
    """A tqdm subclass that reports into ``tracker``.

    Built here rather than declared at module level because tqdm arrives with
    huggingface_hub, and this module has to import on a machine with neither.
    """
    from tqdm.auto import tqdm as _tqdm

    class _TrackedTqdm(_tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            tracker.register(id(self), self.total, getattr(self, "unit", "it"))

        def update(self, n=1):
            tracker.advance(id(self), n or 0)
            return super().update(n)

        def close(self):
            tracker.close(id(self))
            super().close()

    return _TrackedTqdm


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


def download_checkpoint(
    checkpoint: str = DEFAULT_TIMESFM_CHECKPOINT,
    token: str = "",
    progress=None,
) -> str:
    """Fetch the weights, reporting progress. Returns the local path.

    The whole repository, because Tyche does not know which files this
    checkpoint's loader will ask for and guessing wrong produces a download
    that looks complete and then fails on the first forecast. The `forecast`
    CI job prints what actually landed, so that guess can become a measurement
    rather than staying an assumption.

    Resumable by huggingface_hub itself: a second call after a broken
    connection continues rather than restarting.
    """
    from huggingface_hub import snapshot_download

    tracker = DownloadProgress(progress)
    try:
        path = snapshot_download(
            repo_id=checkpoint,
            token=token or None,
            tqdm_class=tracking_tqdm(tracker),
        )
    except Exception as exc:  # noqa: BLE001 — every failure becomes a sentence
        raise RuntimeError(download_failure_message(checkpoint, str(exc))) from exc
    tracker.finish()
    return str(path)


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
