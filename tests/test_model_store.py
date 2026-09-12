# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
tests/test_model_store.py — Tyche

The arithmetic and the wording of "can TimesFM run, and how far along is the
download".

**This suite runs on a machine with neither torch nor huggingface_hub**, which
is the point: :mod:`core.model_store` exists so that the interface can answer
those questions without importing either, and a test that needed them to be
installed would be testing a different module. ``_has_module`` and
``_checkpoint_cached`` are the two seams, and every state is exercised through
them.

What is *not* covered here, stated plainly rather than left to be assumed: no
test in this file has ever seen huggingface_hub emit a progress bar. The
adapter's arithmetic is driven by hand below; the wiring between tqdm and it
is exercised for real by the `forecast` CI job, which downloads the checkpoint
on a runner with a normal network and prints what the tracker made of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import model_store  # noqa: E402
from core.localise import it_bytes  # noqa: E402
from core.model_store import (  # noqa: E402
    NO_CHECKPOINT,
    NO_PACKAGE,
    READY,
    UNKNOWN,
    DiskProgress,
    availability,
    download_failure_message,
)
from core.predictor import METHOD_NAMES, METHODS, method_name  # noqa: E402
from core.version import DEFAULT_TIMESFM_CHECKPOINT  # noqa: E402


@pytest.fixture(autouse=True)
def _the_loader_can_read_weights(monkeypatch):
    """Describe a machine where huggingface_hub can see safetensors.

    It cannot see it here: this suite runs with neither torch nor safetensors
    installed, on purpose, and without this every availability test would stop
    at "the loader is broken" — which is true of the test machine and not of
    the question being asked.

    A test about *that* failure patches it back; monkeypatch inside the test
    wins over a fixture applied before it.
    """
    monkeypatch.setattr(model_store, "missing_loader_packages", lambda: [])


class _Clock:
    """A hand-cranked monotonic clock, so throttling is tested and not waited."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _collect():
    """A progress callback that keeps what it was told."""
    seen: list[tuple[str, float]] = []
    return seen, lambda message, fraction: seen.append((message, fraction))


# ── sizes on screen ──────────────────────────────────────────
class TestByteFormatting:
    def test_it_uses_the_italian_decimal_comma(self):
        assert it_bytes(1_382_400_000) == "1,29 GB"

    def test_small_sizes_do_not_get_spurious_precision(self):
        assert it_bytes(512) == "512 B"
        assert it_bytes(2048) == "2 KB"

    def test_the_unit_changes_at_1024_not_at_1000(self):
        """Downloads are counted in binary units and so is the file manager."""
        assert it_bytes(1000).endswith(" B")
        assert it_bytes(1024) == "1 KB"


# ── the download percentage ──────────────────────────────────
class TestDiskProgress:
    """Measured from the cache, because the tqdm hook produced nothing.

    The version this replaces added up huggingface_hub's progress bars through
    ``tqdm_class``. Every piece of that arithmetic was tested here and the
    status bar still never moved on the owner's machine: whether hf_hub honours
    the hook was a claim about somebody else's library, and no test in this
    file could check it. Bytes on disk are not a claim about anybody's library.
    """

    def _tree(self, tmp_path, sizes):
        for name, size in sizes.items():
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x" * size)
        return tmp_path

    def test_it_counts_what_is_on_disk(self, tmp_path):
        self._tree(tmp_path, {"blobs/a": 300, "snapshots/x/b": 700})
        tracker = DiskProgress(tmp_path, expected=2000)
        tracker.sample()
        assert tracker.downloaded == 1000
        assert tracker.fraction == 0.5

    def test_a_resumed_download_opens_where_it_stopped(self, tmp_path):
        """72% must read as 72%, not as 0%.

        The whole reason this is measured rather than accumulated: a second
        attempt continues from the cache, and a counter that started from zero
        would tell the user the first attempt achieved nothing.
        """
        self._tree(tmp_path, {"blobs/half": 720})
        tracker = DiskProgress(tmp_path, expected=1000)
        tracker.sample()
        assert "72%" in tracker.message()

    def test_the_denominator_does_not_move(self, tmp_path):
        """Asked of the Hub once, before the download, so it cannot grow.

        The previous version summed the per-file bars as they appeared, so its
        total grew during the download and the percentage could fall.
        """
        self._tree(tmp_path, {"a": 100})
        tracker = DiskProgress(tmp_path, expected=1000)
        tracker.sample()
        first = tracker.fraction
        self._tree(tmp_path, {"b": 400})
        tracker.sample()
        assert tracker.fraction > first
        assert "di " + it_bytes(1000) in tracker.message()

    def test_it_never_reports_above_a_hundred_per_cent(self, tmp_path):
        self._tree(tmp_path, {"a": 5000})
        tracker = DiskProgress(tmp_path, expected=1000)
        tracker.sample()
        assert tracker.fraction == 1.0

    def test_a_vanishing_file_does_not_raise(self, tmp_path):
        """hf_hub renames an .incomplete blob into place while this walks.

        A progress indicator that dies on that has failed at its one job.
        """
        tracker = DiskProgress(tmp_path / "not-there", expected=1000)
        tracker.sample()
        assert tracker.downloaded == 0

    def test_it_reports_at_most_once_per_percent(self, tmp_path):
        """Every call becomes a closure queued onto the Tk main thread."""
        seen, report = _collect()
        clock = _Clock()
        size = {"n": 0}
        tracker = DiskProgress(
            tmp_path, expected=10_000_000, report=report, throttle=0.5,
            clock=clock, measure=lambda: size["n"],
        )
        for _ in range(100):
            size["n"] += 1                   # 100 bytes of ten million: 0%
            tracker.sample()
        assert len(seen) == 1, seen

    def test_time_alone_is_enough_to_report(self, tmp_path):
        """A stalled percentage still has to prove the download is alive."""
        seen, report = _collect()
        clock = _Clock()
        tracker = DiskProgress(
            tmp_path, expected=10_000_000, report=report, throttle=0.5,
            clock=clock, measure=lambda: 1,
        )
        tracker.sample()
        before = len(seen)
        tracker.sample()
        assert len(seen) == before
        clock.now += 1.0
        tracker.sample()
        assert len(seen) == before + 1

    def test_without_a_denominator_it_still_says_something(self, tmp_path):
        """The Hub not answering must not mean a silent download."""
        tracker = DiskProgress(tmp_path, expected=0, measure=lambda: 4096)
        tracker.sample()
        assert it_bytes(4096) in tracker.message()
        assert "%" not in tracker.message()

    def test_nothing_is_reported_when_no_callback_was_given(self, tmp_path):
        tracker = DiskProgress(tmp_path, expected=100, measure=lambda: 50)
        assert tracker.sample(force=True) is False


# ── what stands between the user and a forecast ──────────────
class TestAvailability:
    def test_a_missing_package_cannot_be_fixed_by_downloading(self, monkeypatch):
        monkeypatch.setattr(model_store, "_has_module", lambda name: False)
        state = availability()
        assert state.state == NO_PACKAGE
        assert state.can_download is False
        assert state.usable is False

    def test_cached_weights_are_ready(self, monkeypatch):
        monkeypatch.setattr(model_store, "_has_module", lambda name: True)
        monkeypatch.setattr(model_store, "_checkpoint_cached", lambda checkpoint: True)
        state = availability()
        assert state.state == READY
        assert state.ready and state.usable
        assert state.can_download is False

    def test_missing_weights_offer_the_download(self, monkeypatch):
        monkeypatch.setattr(model_store, "_has_module", lambda name: True)
        monkeypatch.setattr(model_store, "_checkpoint_cached", lambda checkpoint: False)
        state = availability()
        assert state.state == NO_CHECKPOINT
        assert state.can_download is True
        assert state.usable is False

    def test_it_does_not_send_the_user_for_a_token_it_does_not_need(self, monkeypatch):
        """The default checkpoint is not gated, and the panel must not imply it is.

        Measured, not remembered: the `checkpoint-licence` CI job asked the
        three model cards and none of them is gated. A "download the weights"
        prompt that also asks for a Hugging Face account sends the user to
        make one for nothing, and this is the sentence that would do it.
        """
        monkeypatch.setattr(model_store, "_has_module", lambda name: True)
        monkeypatch.setattr(model_store, "_checkpoint_cached", lambda checkpoint: False)
        detail = availability(DEFAULT_TIMESFM_CHECKPOINT).detail
        assert "non serve alcun token" in detail

    def test_an_unverifiable_state_still_lets_the_user_try(self, monkeypatch):
        """timesfm present, huggingface_hub not: Tyche cannot check the cache.

        Refusing to offer the method would turn "I could not check" into "it
        does not work", which is a worse answer than letting the attempt speak
        for itself.
        """
        monkeypatch.setattr(
            model_store, "_has_module", lambda name: name == "timesfm3"
        )
        state = availability()
        assert state.state == UNKNOWN
        assert state.usable is True
        assert state.ready is False


class TestTheCacheCheck:
    """A snapshot without weights in it is not a usable checkpoint."""

    def _fake_snapshot(self, monkeypatch, tmp_path, names):
        import sys
        import types

        for name in names:
            (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / name).write_bytes(b"x")
        module = types.ModuleType("huggingface_hub")
        module.snapshot_download = lambda **kwargs: str(tmp_path)
        monkeypatch.setitem(sys.modules, "huggingface_hub", module)

    def test_a_snapshot_with_weights_is_cached(self, monkeypatch, tmp_path):
        self._fake_snapshot(
            monkeypatch, tmp_path, ["config.json", "model.safetensors"]
        )
        assert model_store._checkpoint_cached("org/model") is True

    def test_an_interrupted_download_is_not_cached(self, monkeypatch, tmp_path):
        """Config and tokeniser but no weights: the state the user hit.

        Offline, ``snapshot_download`` can only compare against the file list
        it already has, so a half-finished download resolves happily and the
        path panel said "pronto" over a model that could not load.
        """
        self._fake_snapshot(
            monkeypatch, tmp_path, ["config.json", "tokenizer.json"]
        )
        assert model_store._checkpoint_cached("org/model") is False

    def test_weights_in_a_subdirectory_still_count(self, monkeypatch, tmp_path):
        self._fake_snapshot(monkeypatch, tmp_path, ["torch/model.bin"])
        assert model_store._checkpoint_cached("org/model") is True

    def test_a_miss_is_not_cached(self, monkeypatch, tmp_path):
        import sys
        import types

        module = types.ModuleType("huggingface_hub")

        def raise_it(**kwargs):
            raise OSError("not in the cache")

        module.snapshot_download = raise_it
        monkeypatch.setitem(sys.modules, "huggingface_hub", module)
        assert model_store._checkpoint_cached("org/model") is False


class TestDownloadFailures:
    def test_an_authorisation_failure_names_the_token_and_the_setting(self):
        message = download_failure_message(
            "google/timesfm-3.0-pytorch", "401 Client Error: Unauthorized"
        )
        assert "token" in message.lower()
        assert "Impostazioni" in message

    def test_a_gated_repository_is_recognised_by_the_word_too(self):
        message = download_failure_message("org/model", "Access to this gated repo")
        assert "token" in message.lower()

    def test_an_ordinary_network_failure_does_not_mention_a_token(self):
        """Otherwise every hiccup teaches the reader they need an account."""
        message = download_failure_message("org/model", "Connection reset by peer")
        assert "token" not in message.lower()
        assert "riprova" in message.lower()

    def test_it_says_a_retry_resumes_rather_than_restarts(self):
        message = download_failure_message("org/model", "timed out")
        assert "cache" in message.lower()


class TestTheSlimDownload:
    """A shorter download is only an improvement if it can still be loaded."""

    def test_it_never_excludes_a_weights_format(self):
        """The exclusion list and the acceptance list must not overlap.

        Excluding a format that `_checkpoint_cached` then looks for would
        produce a download the program itself calls incomplete, forever.
        """
        from core.model_store import _WEIGHT_SUFFIXES, SKIPPABLE

        excluded = {pattern.lstrip("*") for pattern in SKIPPABLE}
        assert not excluded & set(_WEIGHT_SUFFIXES)

    def test_it_only_excludes_formats_torch_cannot_read(self):
        """Every entry is another framework's serialisation, or a picture."""
        from core.model_store import SKIPPABLE

        assert set(SKIPPABLE) >= {"*.h5", "*.msgpack", "*.onnx"}
        assert "*.json" not in SKIPPABLE, "the config is not optional"
        assert "*.py" not in SKIPPABLE, "some checkpoints ship their own code"

    def test_a_slim_download_that_lands_no_weights_is_retried_whole(
        self, monkeypatch, tmp_path
    ):
        """The retry is what makes the exclusion safe to have guessed.

        Nobody here can list that repository — Hugging Face answers 403
        through this sandbox's proxy — so the patterns are an informed guess.
        A guess that quietly cost the weights would be the worst failure
        available; this one costs a second attempt.
        """
        calls = []
        empty, full = tmp_path / "empty", tmp_path / "full"
        empty.mkdir()
        full.mkdir()
        (full / "model.safetensors").write_bytes(b"x")

        def fake_snapshot(checkpoint, token, progress, ignore, expected):
            calls.append(tuple(ignore))
            return str(empty if ignore else full)

        monkeypatch.setattr(model_store, "_snapshot", fake_snapshot)
        monkeypatch.setattr(model_store, "expected_download", lambda *a, **k: (0, 0))
        path = model_store.download_checkpoint("org/model")
        assert len(calls) == 2, "a weightless slim download must be retried"
        assert calls[0] and not calls[1], "the retry must exclude nothing"
        assert path == str(full)

    def test_a_slim_download_with_weights_is_not_repeated(
        self, monkeypatch, tmp_path
    ):
        calls = []
        (tmp_path / "model.safetensors").write_bytes(b"x")

        def fake_snapshot(checkpoint, token, progress, ignore, expected):
            calls.append(tuple(ignore))
            return str(tmp_path)

        monkeypatch.setattr(model_store, "_snapshot", fake_snapshot)
        monkeypatch.setattr(model_store, "expected_download", lambda *a, **k: (0, 0))
        model_store.download_checkpoint("org/model")
        assert len(calls) == 1


class TestATruncatedDownload:
    """The owner's actual failure: 882 MB of 1.23 GB, several times, silently.

    The call returned, the panel moved on, and the next screen said the
    weights were missing with no hint that 72% of them were in the cache.
    """

    def _snapshot_returning(self, monkeypatch, tmp_path, sizes):
        """A fake download that writes `sizes` bytes on each attempt in turn."""
        attempts = {"n": 0}
        target = tmp_path / "model.safetensors"

        def fake_snapshot(checkpoint, token, progress, ignore, expected):
            target.write_bytes(b"x" * sizes[min(attempts["n"], len(sizes) - 1)])
            attempts["n"] += 1
            return str(tmp_path)

        monkeypatch.setattr(model_store, "_snapshot", fake_snapshot)
        return attempts

    def test_a_short_download_is_resumed(self, monkeypatch, tmp_path):
        monkeypatch.setattr(model_store, "expected_download", lambda *a, **k: (1, 1000))
        attempts = self._snapshot_returning(monkeypatch, tmp_path, [720, 1000])
        model_store.download_checkpoint("org/model")
        assert attempts["n"] == 2, "a truncated download must be tried again"

    def test_a_complete_download_is_not_repeated(self, monkeypatch, tmp_path):
        monkeypatch.setattr(model_store, "expected_download", lambda *a, **k: (1, 1000))
        attempts = self._snapshot_returning(monkeypatch, tmp_path, [1000])
        model_store.download_checkpoint("org/model")
        assert attempts["n"] == 1

    def test_giving_up_says_how_far_it_got_and_that_it_resumes(
        self, monkeypatch, tmp_path
    ):
        """Silence was the defect. The number and the way out both go in."""
        import pytest

        monkeypatch.setattr(model_store, "expected_download", lambda *a, **k: (1, 1000))
        self._snapshot_returning(monkeypatch, tmp_path, [720])
        with pytest.raises(RuntimeError) as raised:
            model_store.download_checkpoint("org/model", attempts=2)
        message = str(raised.value)
        assert it_bytes(720) in message and it_bytes(1000) in message
        assert "riprende" in message

    def test_without_a_denominator_it_does_not_retry_forever(
        self, monkeypatch, tmp_path
    ):
        """The Hub not answering must not turn one download into three."""
        monkeypatch.setattr(model_store, "expected_download", lambda *a, **k: (0, 0))
        attempts = self._snapshot_returning(monkeypatch, tmp_path, [10])
        model_store.download_checkpoint("org/model")
        assert attempts["n"] == 1


class TestTheDiagnosis:
    """Forty lines a user can paste, from a machine nobody here can see."""

    def test_it_never_raises_however_broken_the_machine(self):
        """A diagnostic that dies on the first missing import diagnoses nothing.

        This suite runs with neither torch nor huggingface_hub installed,
        which is exactly the shape of machine it exists for.
        """
        lines = model_store.diagnose()
        assert isinstance(lines, list) and lines

    def test_it_names_what_is_missing_rather_than_only_that_it_is(self):
        report = "\n".join(model_store.diagnose())
        assert "timesfm3" in report
        assert "huggingface_hub" in report
        assert "torch" in report

    def test_it_says_the_token_is_not_needed_for_the_default(self):
        report = "\n".join(model_store.diagnose())
        assert "non serve per il checkpoint predefinito" in report

    def test_it_reports_the_python_it_is_running_on(self):
        """Half the "it does not work here" reports are a second interpreter."""
        import sys

        assert sys.version.split()[0] in "\n".join(model_store.diagnose())


# ── the display names ────────────────────────────────────────
class TestMethodNames:
    def test_every_identifier_has_a_display_name(self):
        for method in METHODS:
            assert method in METHOD_NAMES
            assert method_name(method) != method or method == METHOD_NAMES[method]

    def test_the_model_is_written_the_way_the_rest_of_the_app_writes_it(self):
        assert method_name("timesfm") == "TimesFM"

    def test_an_unknown_identifier_comes_back_unchanged(self):
        """The map is presentation. It must never be able to hide a method."""
        assert method_name("qualcosa") == "qualcosa"

    def test_the_identifiers_themselves_did_not_change(self):
        """settings.json and --forecast take these; renaming them is breaking.

        The display names exist precisely so that the identifiers do not have
        to move.
        """
        assert METHODS == ("timesfm", "frequenza", "ritardo", "casuale")


class TestAFolderFilledByHand:
    """The way in that does not involve downloading anything.

    The owner's download refused to complete several times, so he fetched the
    file with a browser and put it in a folder — and Tyche could not use it,
    because a hand-made folder is not the ``models--org--name/snapshots``
    layout ``snapshot_download`` resolves. That is the defect these cover.

    **The two filenames are read out of the libraries, not chosen here.**
    ``timesfm3`` branches on ``os.path.isdir`` and hands a directory to
    ``PyTorchModelHubMixin.from_pretrained``, whose local branch opens
    ``config.json`` and ``model.safetensors`` and nothing else.
    """

    def _folder(self, tmp_path, names, root="pesi"):
        return self._fill(tmp_path / root, names)

    def _fill(self, folder, names):
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            (folder / name).write_bytes(b"x" * 16)
        return folder

    def _installed(self, monkeypatch):
        monkeypatch.setattr(model_store, "_has_module", lambda name: True)
        monkeypatch.setattr(model_store, "_checkpoint_cached", lambda checkpoint: False)

    def test_two_files_are_enough(self, monkeypatch, tmp_path):
        self._installed(monkeypatch)
        folder = self._folder(tmp_path, model_store.REQUIRED_FILES)
        state = availability(DEFAULT_TIMESFM_CHECKPOINT, str(folder))
        assert state.state == READY
        assert state.ready and state.usable
        assert state.can_download is False
        assert str(folder) in state.detail

    def test_a_weights_file_on_its_own_is_not_a_checkpoint(self, monkeypatch, tmp_path):
        """``config.json`` is not optional, and saying so beats a stack trace.

        The mixin builds the model from the config and *then* loads the
        tensors into it. A folder holding only the 1,23 GB file looks finished
        to the person who assembled it and fails at load time.
        """
        self._installed(monkeypatch)
        folder = self._folder(tmp_path, ["model.safetensors"])
        state = availability(DEFAULT_TIMESFM_CHECKPOINT, str(folder))
        assert state.state == NO_CHECKPOINT
        assert "config.json" in state.detail

    def test_the_missing_file_is_named(self, monkeypatch, tmp_path):
        self._installed(monkeypatch)
        folder = self._folder(tmp_path, ["config.json"])
        detail = availability(DEFAULT_TIMESFM_CHECKPOINT, str(folder)).detail
        assert "model.safetensors" in detail
        assert str(folder) in detail

    def test_a_folder_that_is_not_there_says_that_and_not_something_else(
        self, monkeypatch, tmp_path
    ):
        self._installed(monkeypatch)
        detail = availability(
            DEFAULT_TIMESFM_CHECKPOINT, str(tmp_path / "non-esiste")
        ).detail
        assert "non esiste" in detail

    def test_the_files_may_sit_one_level_down(self, monkeypatch, tmp_path):
        """Unzipping an archive puts them in a subfolder, and that is fine.

        Refusing that would be refusing over a detail the instruction never
        mentioned.
        """
        self._installed(monkeypatch)
        inner = self._folder(tmp_path / "scaricati", model_store.REQUIRED_FILES)
        state = availability(DEFAULT_TIMESFM_CHECKPOINT, str(tmp_path / "scaricati"))
        assert state.state == READY
        assert str(inner) in state.detail

    def test_the_loader_is_pointed_at_the_folder_and_not_at_the_repository(
        self, tmp_path
    ):
        """The whole point: ``checkpoint_path`` becomes a directory.

        Passing the repository id would send timesfm3 back to Hugging Face for
        a file that is already on the disk, which is the failure the folder
        exists to route around.
        """
        folder = self._folder(tmp_path, model_store.REQUIRED_FILES)
        assert model_store.resolve_checkpoint(
            DEFAULT_TIMESFM_CHECKPOINT, str(folder)
        ) == str(folder)

    def test_without_a_folder_the_repository_id_is_still_what_is_used(
        self, monkeypatch
    ):
        monkeypatch.setattr(model_store, "local_checkpoint", lambda checkpoint: None)
        assert (
            model_store.resolve_checkpoint(DEFAULT_TIMESFM_CHECKPOINT, "")
            == DEFAULT_TIMESFM_CHECKPOINT
        )

    def test_a_broken_folder_is_reported_even_when_the_download_worked(
        self, monkeypatch, tmp_path
    ):
        """Otherwise the setting is silently ignored and nothing ever says so.

        The weights are cached, so TimesFM runs and the state is READY — but
        the folder the user typed is wrong, and no other screen will ever
        mention it again.
        """
        monkeypatch.setattr(model_store, "_has_module", lambda name: True)
        monkeypatch.setattr(model_store, "_checkpoint_cached", lambda checkpoint: True)
        folder = self._folder(tmp_path, ["config.json"])
        state = availability(DEFAULT_TIMESFM_CHECKPOINT, str(folder))
        assert state.ready
        assert "model.safetensors" in state.detail

    def test_a_usable_folder_downloads_nothing(self, monkeypatch, tmp_path):
        folder = self._folder(tmp_path, model_store.REQUIRED_FILES)

        def refuse(*args, **kwargs):
            raise AssertionError("nothing should be downloaded")

        monkeypatch.setattr(model_store, "download_checkpoint", refuse)
        model_store.ensure_checkpoint(
            DEFAULT_TIMESFM_CHECKPOINT, folder=str(folder)
        )

    def test_a_cache_huggingface_hub_will_not_resolve_is_read_directly(
        self, monkeypatch, tmp_path
    ):
        """The repair. hf_hub says no; the folder plainly holds the weights.

        A cache assembled by hand, or one whose ``refs`` were lost, answers
        ``local_files_only`` with a miss while the two files sit there. Asking
        the library first stays the rule — this is the second opinion.
        """
        monkeypatch.setattr(model_store, "_has_module", lambda name: True)
        monkeypatch.setattr(model_store, "_checkpoint_cached", lambda checkpoint: False)
        snapshot = self._fill(
            tmp_path / "models--org--model" / "snapshots" / "abc123",
            model_store.REQUIRED_FILES,
        )
        monkeypatch.setattr(
            model_store, "_repo_folder", lambda checkpoint: tmp_path / "models--org--model"
        )
        state = availability("org/model")
        assert state.state == READY
        assert model_store.resolve_checkpoint("org/model") == str(snapshot)

    def test_the_cache_of_another_model_is_not_mistaken_for_this_one(
        self, monkeypatch, tmp_path
    ):
        """``repo_cache_dir`` falls back to the cache root; this must not.

        Searching the root would find some other model's ``config.json`` and
        report a checkpoint that was never asked for.
        """
        self._fill(
            tmp_path / "models--altro--modello" / "snapshots" / "x",
            model_store.REQUIRED_FILES,
        )
        # The root holds another model and this repository's folder does not
        # exist — which is exactly when repo_cache_dir() answers with the root.
        monkeypatch.setattr(
            model_store,
            "_repo_folder",
            lambda checkpoint: tmp_path / "models--org--model",
        )
        monkeypatch.setattr(model_store, "repo_cache_dir", lambda checkpoint: tmp_path)
        assert model_store.local_checkpoint("org/model") is None


class TestTheLoaderTheHubCannotSee:
    """Importable is not the same as visible, and the difference is a release.

    The owner's build had the weights on disk, every screen said «pronto», and
    pressing «Genera» produced ``NameError: name 'safetensors' is not
    defined`` after a wait. Nothing was wrong with the download or the
    checkpoint: huggingface_hub asks ``importlib.metadata`` whether
    safetensors is installed, the frozen bundle carried the module without its
    ``.dist-info``, and so the mixin never imported the name it later used.
    """

    def test_a_module_without_metadata_does_not_count_as_installed(self):
        """``json`` imports on every machine and is not a distribution.

        This is the whole distinction in one line: ``find_spec`` would say yes
        and huggingface_hub says no, so asking the cheap question would have
        reported a working machine.
        """
        import importlib.util

        assert importlib.util.find_spec("json") is not None
        assert model_store._visible_to_hub("json") is False

    def test_an_invisible_loader_is_not_ready_however_complete_the_weights_are(
        self, monkeypatch, tmp_path
    ):
        folder = tmp_path / "pesi"
        folder.mkdir()
        for name in model_store.REQUIRED_FILES:
            (folder / name).write_bytes(b"x" * 16)
        monkeypatch.setattr(model_store, "_has_module", lambda name: True)
        monkeypatch.setattr(model_store, "_checkpoint_cached", lambda checkpoint: True)
        monkeypatch.setattr(
            model_store, "missing_loader_packages", lambda: ["safetensors"]
        )

        state = availability(DEFAULT_TIMESFM_CHECKPOINT, str(folder))
        assert state.state == NO_PACKAGE
        assert state.ready is False
        assert state.can_download is False, (
            "downloading 1,23 GB again cannot fix a missing package"
        )
        assert "safetensors" in state.detail

    def test_a_frozen_build_is_told_to_reinstall_and_not_to_run_pip(
        self, monkeypatch
    ):
        """There is no console in the packaged build, so pip is not advice."""
        monkeypatch.setattr(model_store, "_frozen", lambda: True)
        detail = model_store._loader_detail(["safetensors"])
        assert "pip" not in detail
        assert "release" in detail

    def test_a_source_install_is_told_the_command(self, monkeypatch):
        monkeypatch.setattr(model_store, "_frozen", lambda: False)
        detail = model_store._loader_detail(["safetensors"])
        assert "pip install safetensors" in detail

    def test_the_other_methods_are_not_taken_down_with_it(self, monkeypatch):
        monkeypatch.setattr(
            model_store, "missing_loader_packages", lambda: ["safetensors"]
        )
        monkeypatch.setattr(model_store, "_has_module", lambda name: True)
        assert "altri tre metodi" in availability().detail

    def test_the_diagnosis_names_it_as_the_cause(self, monkeypatch):
        monkeypatch.setattr(model_store, "_visible_to_hub", lambda name: False)
        report = "\n".join(model_store.diagnose())
        assert "safetensors visibile a huggingface_hub: NO" in report

    def test_the_diagnosis_says_whether_this_is_a_packaged_build(self):
        """Which decides the remedy, so support cannot start without it."""
        report = "\n".join(model_store.diagnose())
        assert "eseguito da:" in report
