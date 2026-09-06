# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""
tests/test_release_workflow.py — Tyche

Tests for ``.github/workflows/release.yml``, ``.github/release-body.md`` and
``CHANGELOG.md``.

Only GitHub Actions can actually run the workflow, so these parse the
checked-in files instead. They are worth having because the release path runs
about twice a year: every bug in it is found by a person waiting for a
download, months after the change that caused it, and each of the guards below
corresponds to a mistake already shipped once across these projects — a
release published as an invisible draft, notes that were the raw commit log,
and a download whose name promised a version the program did not report.

PyYAML is imported hard, not via ``importorskip``. It is in
``requirements-dev.txt``; a run without it is a broken environment, not a
lighter one, and a skip here would silently stop testing the file that
publishes the releases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

WORKFLOW = REPO / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
BODY = REPO / ".github" / "release-body.md"
CHANGELOG = REPO / "CHANGELOG.md"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow() -> dict:
    return load(WORKFLOW)


@pytest.fixture(scope="module")
def steps(workflow) -> list[dict]:
    return workflow["jobs"]["release"]["steps"]


def step_text(steps: list[dict]) -> str:
    """Every ``run:`` in the job, concatenated. Enough for "does it do X"."""
    return "\n".join(step.get("run", "") for step in steps)


def suite_step(steps: list[dict]) -> dict:
    """The step that runs the suite.

    Not named ``test_*``: pytest would collect this helper as a test case,
    which it did, and then warn that the test returned a dict.

    Matched on ``-m pytest`` and not on the bare word: the dependency-install
    step also contains "pytest", and selecting that one instead made two of
    the checks below assert things about a pip line while reporting green.
    """
    return next(s for s in steps if "-m pytest" in s.get("run", ""))


def triggers(workflow) -> dict:
    # PyYAML's 1.1 reader parses a bare ``on:`` key as the boolean True. That
    # is a quirk of the library, not of the workflow file.
    return workflow.get("on") or workflow[True]


# ─────────────────────────────────────────────────────────────
# The files exist and refer to each other
# ─────────────────────────────────────────────────────────────

def test_the_release_files_all_exist():
    for path in (WORKFLOW, BODY, CHANGELOG, REPO / "tools" / "release_notes.py"):
        assert path.exists(), f"{path.relative_to(REPO)} is missing"


def test_the_workflow_only_runs_scripts_that_are_in_the_repository():
    """A workflow calling a script nobody kept is found at release time."""
    text = step_text(load(WORKFLOW)["jobs"]["release"]["steps"])
    for line in text.splitlines():
        if "tools/" in line:
            script = line.split("tools/")[1].split()[0].strip('"')
            assert (REPO / "tools" / script).exists(), f"tools/{script} is missing"


# ─────────────────────────────────────────────────────────────
# Triggers
# ─────────────────────────────────────────────────────────────

def test_a_version_tag_starts_a_release(workflow):
    assert triggers(workflow)["push"]["tags"] == ["v*"]


def test_it_can_also_be_run_by_hand_with_a_tag(workflow):
    inputs = triggers(workflow)["workflow_dispatch"]["inputs"]
    assert inputs["tag"]["required"] is True


def test_it_does_not_also_fire_on_release_published(workflow):
    """Both events fire when a release is published from the UI.

    Two runs would then race to write the same notes onto the same release.
    """
    assert "release" not in triggers(workflow)


def test_it_can_write_to_the_repository(workflow):
    assert workflow["permissions"]["contents"] == "write"


def test_two_runs_on_one_tag_cannot_race(workflow):
    concurrency = workflow["concurrency"]
    assert "release-" in concurrency["group"]
    # Not cancel-in-progress: a half-cancelled publish is worse than a slow one.
    assert concurrency["cancel-in-progress"] is False


# ─────────────────────────────────────────────────────────────
# What has to happen before anything is published
# ─────────────────────────────────────────────────────────────

def test_the_tag_shape_is_validated(steps):
    assert "is not a version tag" in step_text(steps)


def test_it_checks_out_the_tag_and_not_the_default_branch(steps):
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert "tag" in checkout["with"]["ref"]


def test_the_linter_runs(steps):
    assert "ruff check ." in step_text(steps)


def test_the_whole_suite_runs_with_the_gui_required(steps):
    """A release must not be published on a run that skipped the interface."""
    step = suite_step(steps)
    assert step["env"]["TYCHE_REQUIRE_GUI"] == "1"
    assert "xvfb-run" in step["run"]


def test_the_tag_must_match_the_version_the_program_reports(steps):
    """Otherwise v2.3.0 can ship a program that answers 0.1.0."""
    text = step_text(steps)
    assert "main.py --version" in text
    assert "core/version.py says" in text


def test_the_release_is_created_after_the_tests_and_not_before(steps):
    """Order is the only thing making this a gate rather than a bystander."""
    names = [s.get("name", "") for s in steps]
    runs = [s.get("run", "") for s in steps]
    tested = next(i for i, r in enumerate(runs) if "-m pytest" in r)
    published = next(i for i, r in enumerate(runs) if "gh release create" in r)
    assert tested < published, f"tests run after publishing: {names}"


# ─────────────────────────────────────────────────────────────
# The notes
# ─────────────────────────────────────────────────────────────

def test_the_notes_come_from_a_file_and_not_from_the_commit_log(steps):
    """--generate-notes emits the commit log, which is engineering shorthand."""
    text = step_text(steps)
    assert "--notes-file" in text
    assert "--generate-notes" not in text


def test_a_release_that_already_exists_is_updated_rather_than_left_as_a_draft(steps):
    """Publishing from GitHub's UI creates the tag, so `create` fails."""
    text = step_text(steps)
    assert "gh release edit" in text
    assert "--draft=false" in text


def test_the_release_gets_a_title(steps):
    assert "--title" in step_text(steps)


def test_the_notes_compose_for_the_current_version():
    """The version in core/version.py must have something written about it."""
    from core.version import __version__
    from tools.release_notes import compose

    notes = compose(__version__)
    assert f"Cosa c'è in v{__version__}" in notes
    assert len(notes) > 500


def test_composing_notes_for_an_unwritten_version_is_an_error():
    from tools.release_notes import compose

    with pytest.raises(SystemExit, match="no section"):
        compose("99.99.99")


def test_the_changelog_has_a_section_for_the_current_version():
    from core.version import __version__
    from tools.release_notes import changelog_section

    body, _ = changelog_section(__version__, CHANGELOG.read_text(encoding="utf-8"))
    assert body.strip()


def test_the_changelog_parser_stops_at_the_next_version_heading():
    from tools.release_notes import changelog_section

    text = "# Changelog\n\n## [2.0.0] — 2026-01-01\n\nsecond\n\n## [1.0.0] — 2025-01-01\n\nfirst\n"
    assert changelog_section("2.0.0", text)[0] == "second"
    assert changelog_section("1.0.0", text)[0] == "first"


def test_the_release_body_says_what_was_verified():
    """The page has to say what the badge on it means."""
    body = BODY.read_text(encoding="utf-8")
    assert "TYCHE_REQUIRE_GUI" in body


def test_the_static_notes_do_not_hardcode_an_archive_name():
    """The download block is written by the job that built the archive.

    Naming the file in the preamble instead would put the version in two
    places, and the two would disagree the first time one of them was edited.
    """
    body = BODY.read_text(encoding="utf-8").lower()
    for promise in (".zip", ".tar.gz"):
        assert promise not in body, f"the preamble names a {promise}; the build job writes that"


def test_the_notes_do_not_promise_platforms_nobody_builds():
    """A release page listing archives nobody built is the worst kind.

    Only Windows is built, so only Windows may be mentioned as a download.
    """
    workflow = load(WORKFLOW)
    runners = {job["runs-on"] for job in workflow["jobs"].values()}
    assert "macos-latest" not in runners
    body = BODY.read_text(encoding="utf-8")
    assert "Non esiste un pacchetto per macOS o Linux" in WORKFLOW.read_text(encoding="utf-8")
    assert "allegato un pacchetto per Windows" in body


# ─────────────────────────────────────────────────────────────
# The Windows build
# ─────────────────────────────────────────────────────────────

def test_the_build_files_exist():
    for path in (REPO / "Tyche.spec", REPO / "build.py",
                 REPO / "requirements-build.txt", REPO / "packaging" / "start.cmd"):
        assert path.exists(), f"{path.relative_to(REPO)} is missing"


def test_the_launcher_stays_pure_ascii():
    """A console inherits the machine's OEM code page, not UTF-8.

    The launcher's messages are Italian like everything else, but an accented
    letter written as UTF-8 reaches an Italian Windows console decoded as
    cp850 and arrives as mojibake — in the one place a user cannot skip past.
    The phrasing avoids accents instead; this fails if somebody types one in.
    """
    text = (REPO / "packaging" / "start.cmd").read_bytes()
    offending = [b for b in text if b > 0x7F]
    assert not offending, f"start.cmd has {len(offending)} non-ASCII byte(s)"


def test_the_windows_job_builds_on_windows():
    """PyInstaller does not cross-compile: a .exe needs a Windows runner."""
    job = load(WORKFLOW)["jobs"]["windows"]
    assert job["runs-on"] == "windows-latest"


def test_the_windows_job_waits_for_the_tests():
    """Nothing is built from a commit that failed them."""
    assert load(WORKFLOW)["jobs"]["windows"]["needs"] == "release"


def test_the_bundle_is_smoke_tested_before_it_is_uploaded():
    steps = load(WORKFLOW)["jobs"]["windows"]["steps"]
    runs = [s.get("run", "") for s in steps]
    checked = next(i for i, r in enumerate(runs) if "--self-check" in r)
    uploaded = next(i for i, r in enumerate(runs) if "gh release upload" in r)
    assert checked < uploaded


def test_the_smoke_test_is_more_than_version():
    """--version exits before the toolkit is imported and proves almost nothing."""
    text = "\n".join(s.get("run", "") for s in load(WORKFLOW)["jobs"]["windows"]["steps"])
    assert "autodiagnosi: SUPERATA" in text
    assert "sistema grafico" in text
    # A bundle that silently lost TimesFM would pass everything else.
    assert "timesfm: nel pacchetto" in text


def test_the_bundle_version_must_match_the_tag_too():
    text = "\n".join(s.get("run", "") for s in load(WORKFLOW)["jobs"]["windows"]["steps"])
    assert "the bundle reports" in text


def test_the_launcher_is_checked_both_ways():
    """It has to start the program, and refuse a binary that fails its digest."""
    text = "\n".join(s.get("run", "") for s in load(WORKFLOW)["jobs"]["windows"]["steps"])
    assert "the launcher did not start Tyche" in text
    assert "started a binary that failed its checksum" in text


def test_the_archive_checksum_reaches_the_notes():
    """A digest that travels inside the archive can only prove it is undamaged."""
    text = "\n".join(s.get("run", "") for s in load(WORKFLOW)["jobs"]["windows"]["steps"])
    assert "gh release edit" in text
    assert "<!-- download -->" in text


def test_the_notes_step_forces_utf8_on_windows():
    """The failure this exists for, from the first real release.

    Windows defaults Python's stdout to cp1252 and the notes carry an em dash
    and a warning sign. body.md was written correctly and then `print(body)`
    raised UnicodeEncodeError, `bash -e` failed the step, and `gh release edit`
    never ran — so the archive was attached and the download section was not.
    Writing the file was already explicitly UTF-8; echoing it to the log was
    the part that was not.
    """
    step = next(
        s for s in load(WORKFLOW)["jobs"]["windows"]["steps"]
        if "download section" in s.get("name", "")
    )
    assert step["env"]["PYTHONIOENCODING"] == "utf-8"


def test_the_notes_step_does_not_echo_the_whole_body():
    """Printing it is what crashed. A length is enough for a log."""
    step = next(
        s for s in load(WORKFLOW)["jobs"]["windows"]["steps"]
        if "download section" in s.get("name", "")
    )
    assert "print(body)" not in step["run"]


def test_the_notes_block_is_a_raw_string():
    r"""It contains a PowerShell `.\` path, and `\{` is an invalid escape.

    Ruff caught this same mistake in this very docstring, which is a fair
    demonstration that the rule earns its place.
    """
    step = next(
        s for s in load(WORKFLOW)["jobs"]["windows"]["steps"]
        if "download section" in s.get("name", "")
    )
    assert 'block = rf"""' in step["run"]


def test_the_spec_builds_a_folder_and_not_one_file():
    """Bundling PyTorch into onefile means unpacking it on every launch."""
    spec = (REPO / "Tyche.spec").read_text(encoding="utf-8")
    assert "COLLECT(" in spec
    assert "exclude_binaries=True" in spec


def test_the_spec_collects_what_pyinstaller_cannot_see():
    spec = (REPO / "Tyche.spec").read_text(encoding="utf-8")
    # customtkinter's themes are package data; timesfm3 is imported lazily by
    # core/forecaster.py, so static analysis never finds it.
    assert 'collect_data_files("customtkinter")' in spec
    assert "timesfm3" in spec


def test_the_spec_excludes_readline_for_the_licensing_reason():
    """libreadline is GPL-3.0-or-later with no linking exception."""
    spec = (REPO / "Tyche.spec").read_text(encoding="utf-8")
    assert '"readline"' in spec and '"rlcompleter"' in spec


def test_pyinstaller_is_a_build_dependency_and_not_a_runtime_one():
    assert "pyinstaller" in (REPO / "requirements-build.txt").read_text(encoding="utf-8").lower()
    assert "pyinstaller" not in (REPO / "requirements.txt").read_text(encoding="utf-8").lower()


def test_the_release_body_keeps_the_disclaimer():
    """It is a lottery program. The page that offers it has to say so."""
    body = BODY.read_text(encoding="utf-8")
    assert "non può aiutarti a vincere" in body
    # Italian thousands separator: the page is Italian, so is the number.
    assert "622.614.630" in body


# ─────────────────────────────────────────────────────────────
# Only one release survives, and the order is the safety
# ─────────────────────────────────────────────────────────────

def _windows_steps():
    return load(WORKFLOW)["jobs"]["windows"]["steps"]


def _cleanup_step():
    for step in _windows_steps():
        if "gh release delete" in step.get("run", ""):
            return step
    raise AssertionError("no step deletes the older releases")


def test_only_the_current_release_is_kept():
    """The repository holds exactly one release, and this is what enforces it."""
    run = _cleanup_step()["run"]
    assert "--cleanup-tag" in run, "the tag has to go with the release"


def test_the_cleanup_runs_after_the_archive_is_uploaded():
    """Deleting the old release before the new one is complete is the disaster.

    A failure between the two would leave the repository with nothing to
    download, which is worse than any number of stale releases.
    """
    runs = [s.get("run", "") for s in _windows_steps()]
    uploaded = next(i for i, r in enumerate(runs) if "gh release upload" in r)
    notes = next(i for i, r in enumerate(runs) if "--notes-file body.md" in r)
    deleted = next(i for i, r in enumerate(runs) if "gh release delete" in r)
    assert uploaded < deleted, "the cleanup runs before the upload"
    assert notes < deleted, "the cleanup runs before the notes are written"
    assert deleted == len(runs) - 1, "the cleanup is not the final step"


def test_the_cleanup_does_not_run_when_something_failed():
    """`if: always()` on a destructive step turns a bad build into data loss."""
    step = _cleanup_step()
    condition = str(step.get("if", ""))
    assert "always()" not in condition
    assert "failure()" not in condition


def test_the_cleanup_refuses_to_run_against_a_release_with_no_asset():
    """An upload that failed quietly must not cost every version at once."""
    run = _cleanup_step()["run"]
    assert "--json assets" in run
    assert "refusing to delete" in run


def test_the_cleanup_never_deletes_the_release_it_just_published():
    """Matched by tag, never by position or date."""
    run = _cleanup_step()["run"]
    assert '[ "$old" = "$TAG" ] && continue' in run


# ─────────────────────────────────────────────────────────────
# CI and release must not drift apart
# ─────────────────────────────────────────────────────────────

def test_the_licence_check_is_manual_and_cannot_fail_a_build():
    """A diagnostic that asks a third party a question is not a test.

    The checkpoint's licence is a fact about someone else's model card. It can
    change without anything in this repository changing, and a scheduled job
    that turned that into a red build would be reporting Google's paperwork as
    a Tyche regression. Manual dispatch, prints, never asserts.
    """
    job = load(CI_WORKFLOW)["jobs"]["checkpoint-licence"]
    assert job["if"] == "github.event_name == 'workflow_dispatch'"
    run = "\n".join(s.get("run", "") for s in job["steps"])
    assert "assert" not in run, "the licence check must report, not assert"
    # The three checkpoints that matter: Tyche's default, the one Argus used
    # before 1.1.0, and the older 200M.
    for checkpoint in ("timesfm-3.0-pytorch", "timesfm-2.5-200m-pytorch"):
        assert checkpoint in run


def test_ci_greps_for_what_the_program_actually_says_with_no_archive():
    """A grep in a workflow is a copy of a string the program owns.

    The translation to Italian left ``grep -q "No archive at"`` in ci.yml
    looking for English the program no longer prints, and the build went red on
    a step that was testing nothing. The literal lives in ``main.NO_ARCHIVE``;
    this asserts the workflow is still looking for it.
    """
    from main import NO_ARCHIVE

    text = "\n".join(
        s.get("run", "") for s in load(CI_WORKFLOW)["jobs"]["test"]["steps"]
    )
    assert f'grep -q "{NO_ARCHIVE}"' in text


def test_ci_and_release_run_the_same_test_command():
    """Two ways of running the suite is two ways for one of them to rot."""
    ci = suite_step(load(CI_WORKFLOW)["jobs"]["test"]["steps"])
    rel = suite_step(load(WORKFLOW)["jobs"]["release"]["steps"])
    assert ci["run"].strip() == rel["run"].strip()
    assert ci["env"]["TYCHE_REQUIRE_GUI"] == rel["env"]["TYCHE_REQUIRE_GUI"]
