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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import model_store  # noqa: E402
from core.localise import it_bytes  # noqa: E402
from core.model_store import (  # noqa: E402
    NO_CHECKPOINT,
    NO_PACKAGE,
    READY,
    UNKNOWN,
    DownloadProgress,
    availability,
    download_failure_message,
)
from core.predictor import METHOD_NAMES, METHODS, method_name  # noqa: E402
from core.version import DEFAULT_TIMESFM_CHECKPOINT  # noqa: E402


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
class TestDownloadProgress:
    def test_byte_bars_add_up_across_files(self):
        tracker = DownloadProgress()
        tracker.register(1, 1000, "B")
        tracker.register(2, 3000, "B")
        tracker.advance(1, 500)
        tracker.advance(2, 500)
        assert tracker.total == 4000
        assert tracker.downloaded == 1000
        assert tracker.fraction == 0.25

    def test_the_file_counter_is_not_counted_as_bytes(self):
        """hf_hub's outer bar counts files; adding it to the bytes is nonsense.

        Five files would put five bytes in the denominator of a gigabyte, and
        the percentage would be right to within a rounding error — which is
        why this is worth a test rather than an inspection.
        """
        tracker = DownloadProgress()
        tracker.register(1, 5, "it")          # "Fetching 5 files"
        tracker.register(2, 1000, "B")
        tracker.advance(1, 2)
        tracker.advance(2, 250)
        assert tracker.total == 1000
        assert tracker.fraction == 0.25
        assert "2 file su 5" in tracker.message()

    def test_the_message_always_shows_what_the_percentage_is_of(self):
        """A percentage that can fall needs its denominator beside it.

        The bars are created as the workers reach the files, so the total
        grows during the download and the percentage can go backwards. That is
        honest arithmetic on incomplete knowledge, and it looks like a bug
        unless the reader can see the denominator grow too.
        """
        tracker = DownloadProgress()
        tracker.register(1, 1000, "B")
        tracker.advance(1, 800)
        first = tracker.message()
        assert "80%" in first and it_bytes(1000) in first

        tracker.register(2, 3000, "B")
        second = tracker.message()
        assert "20%" in second and it_bytes(4000) in second

    def test_a_closed_bar_counts_as_a_whole_file(self):
        """tqdm updates in chunks and the last one can be missed."""
        tracker = DownloadProgress()
        tracker.register(1, 1000, "B")
        tracker.advance(1, 990)
        tracker.close(1)
        assert tracker.downloaded == 1000

    def test_it_reports_at_most_once_per_percent(self):
        """A 1.3 GB download updates thousands of times a second.

        Every call becomes a closure queued onto the Tk main thread, so an
        unthrottled tracker makes the window unresponsive while reporting how
        smoothly it is going.
        """
        seen, report = _collect()
        clock = _Clock()
        tracker = DownloadProgress(report, throttle=0.5, clock=clock)
        tracker.register(1, 10_000, "B")
        for _ in range(100):                       # 100 × 1 byte: 0% throughout
            tracker.advance(1, 1)
        assert len(seen) <= 2                      # the register, and one more

    def test_time_alone_is_enough_to_report(self):
        """A stalled percentage still has to prove the download is alive."""
        seen, report = _collect()
        clock = _Clock()
        tracker = DownloadProgress(report, throttle=0.5, clock=clock)
        tracker.register(1, 10_000_000, "B")
        before = len(seen)
        tracker.advance(1, 1)
        assert len(seen) == before                 # same percent, same second
        clock.now += 1.0
        tracker.advance(1, 1)
        assert len(seen) == before + 1

    def test_a_new_percent_reports_immediately(self):
        seen, report = _collect()
        tracker = DownloadProgress(report, throttle=99.0, clock=_Clock())
        tracker.register(1, 100, "B")
        before = len(seen)
        tracker.advance(1, 40)
        assert len(seen) == before + 1
        assert "40%" in seen[-1][0]

    def test_the_fraction_reaches_the_caller_and_not_only_the_words(self):
        seen, report = _collect()
        tracker = DownloadProgress(report, throttle=0.0, clock=_Clock())
        tracker.register(1, 200, "B")
        tracker.advance(1, 100)
        assert seen[-1][1] == 0.5

    def test_nothing_is_reported_when_no_callback_was_given(self):
        tracker = DownloadProgress()
        tracker.register(1, 100, "B")
        assert tracker.maybe_report(force=True) is False


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
