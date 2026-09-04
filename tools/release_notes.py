# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
tools/release_notes.py — Tyche

Composes the text that appears on a release page: the standing preamble in
``.github/release-body.md``, then this version's section of ``CHANGELOG.md``.

    python tools/release_notes.py 0.1.0 > notes.md

Two things it deliberately is not.

It is **not** ``gh release --generate-notes``, which emits the commit log. A
commit log is engineering shorthand written for the people who already know
what changed; on a first release it is the entire history of the project. What
a release page needs is a description of the thing being downloaded.

And the notes are **not** written into the workflow. A workflow file is the
wrong place for prose: editing it to fix a typo re-runs nothing and reviews
badly, and the text ends up escaped inside YAML. Two files, one of which is
the changelog that should exist anyway.

A missing changelog section is an error rather than an empty heading. Tagging
a version nobody wrote anything about is a mistake worth catching at the point
where it is still cheap to fix.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PREAMBLE = REPO / ".github" / "release-body.md"
CHANGELOG = REPO / "CHANGELOG.md"

# "## [0.1.0] — 2026-09-04", and the looser spellings a hand-edited file grows:
# a plain hyphen instead of an em dash, no date at all, no brackets.
_HEADING = re.compile(r"^##\s+\[?v?(?P<version>[0-9][^\]\s]*)\]?\s*(?:[—–-]\s*(?P<date>\S+))?\s*$")


def changelog_section(version: str, text: str) -> tuple[str, str | None]:
    """``(body, date)`` for one version's section of a changelog.

    Raises :class:`KeyError` when the version has no section, which is the
    check that stops a tag being published with nothing to say about it.
    """
    lines = text.splitlines()
    start = None
    date = None
    for i, line in enumerate(lines):
        match = _HEADING.match(line)
        if not match:
            continue
        if start is not None:
            # The next version heading ends this section.
            return "\n".join(lines[start:i]).strip("\n"), date
        if match.group("version") == version:
            start, date = i + 1, match.group("date")
    if start is None:
        raise KeyError(version)
    return "\n".join(lines[start:]).strip("\n"), date


def compose(version: str, tag: str | None = None) -> str:
    """The whole release body: preamble, then this version's changes."""
    tag = tag or f"v{version}"
    preamble = PREAMBLE.read_text(encoding="utf-8").rstrip("\n")
    preamble = preamble.replace("{{VERSION}}", version).replace("{{TAG}}", tag)

    try:
        section, _ = changelog_section(version, CHANGELOG.read_text(encoding="utf-8"))
    except KeyError:
        raise SystemExit(
            f"CHANGELOG.md has no section for {version}. Add a '## [{version}]' "
            "heading describing what changed, then tag."
        ) from None
    if not section.strip():
        raise SystemExit(f"the CHANGELOG.md section for {version} is empty.")

    return f"{preamble}\n\n---\n\n## What is in {tag}\n\n{section}\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        print("usage: python tools/release_notes.py VERSION", file=sys.stderr)
        return 2
    print(compose(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
