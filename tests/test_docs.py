#!/usr/bin/env python
# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""Guards against the documentation drifting away from the product.

The other five products in this family share an English README skeleton, so a
reader who has found something in one knows where to look in the others.
**Tyche deliberately does not.** SuperEnalotto is an Italian game and 0.2.0
translated everything a user sees; CLAUDE.md's "language boundary" section
records that as a decision rather than an oversight. Imposing the English
skeleton here would undo it.

So what is shared is the *guarantee*, not the wording: the sections are pinned
in order, every internal link resolves, every referenced image exists, the
licensing story is stated where a reader meets it, and no placeholder survived
into a published document. Each of those corresponds to a mistake already
shipped once across these projects.

The licensing tests are the ones with teeth. Tyche is AGPL-3.0-or-later and
nothing else — no commercial tier, no CLA, none of the dual-licensing
apparatus Orion, Iris and Proteus carry. A stray sentence offering to sell a
licence would be offering something that does not exist, and a README that
stopped warning about the TimesFM weights would bury the one restriction a
reader must not miss.
"""

from __future__ import annotations

import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_NAME = "Tyche"
CONTACT = "marco.lombardo@gmail.com"

#: Tyche's own README sections, in order. Not the shared English skeleton —
#: see the module docstring — but pinned all the same, so that reordering or
#: renaming one is a deliberate edit to this list rather than something that
#: happens to a document nobody is watching.
README_SKELETON = (
    "Che cosa fa",
    "Installazione",
    "Da dove vengono i dati",
    "Che cosa hanno trovato i test",
    "«Non abbiamo trovato niente» oppure «non avremmo potuto trovarlo»",
    "Sistemi e SuperStar",
    "Le probabilità, che nessun metodo cambia",
    "Interrogare l'archivio",
    "Come viene usato TimesFM",
    "Licenza",
    "Eseguire i test",
    "Release",
)


def read(name: str) -> str:
    with open(os.path.join(REPO, name), encoding="utf-8") as fh:
        return fh.read()


def headings(text: str, level: int) -> list[str]:
    """Every heading of exactly `level`, in order, outside code fences."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = re.match(rf"^#{{{level}}} (?!#)(.+)$", line)
        if match:
            found.append(match.group(1).strip())
    return found


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_the_readme_keeps_its_sections_in_order():
    assert tuple(headings(read("README.md"), 2)) == README_SKELETON


def test_every_internal_readme_link_points_at_a_heading_that_exists():
    """A restructure breaks the links before it breaks anything else.

    The slug rules are GitHub's: lowercase, punctuation stripped, spaces
    mapped to `-` and *not* collapsed — so `## A & B` is `#a--b`. Getting that
    wrong here would make this test lie in the reassuring direction.
    """
    text = read("README.md")
    available = set()
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = re.match(r"^#{1,6} (.+)$", line)
        if not match:
            continue
        slug = match.group(1).strip().lower()
        slug = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", slug)
        slug = re.sub(r"[`*]", "", slug)
        slug = re.sub(r"[^\w\s-]", "", slug)
        available.add(re.sub(r"[ \t]", "-", slug.strip()))

    broken = sorted({t for t in re.findall(r"\]\(#([\w-]+)\)", text) if t not in available})
    assert not broken, f"README links to headings that do not exist: {broken}"


def test_every_referenced_image_exists():
    """A renamed capture must not leave a broken image on the front page."""
    missing = [
        target
        for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", read("README.md"))
        if not target.startswith("http")
        and not os.path.exists(os.path.join(REPO, target))
    ]
    assert not missing, f"README references missing images: {missing}"


def test_the_readme_carries_no_dollar_sign():
    """CLAUDE.md's rule, enforced.

    GitHub's restricted KaTeX subset has two expensive traps: a bare `_`
    inside `\\text{}` is rejected outright, and one stray `$` re-pairs every
    formula after it, so a document renders correctly until somebody adds a
    price and then silently mangles everything below. Tyche writes the handful
    of formulas it needs as prose or inline code and is immune to both.
    """
    stray = [
        f"{n}: {line.strip()}"
        for n, line in enumerate(read("README.md").splitlines(), 1)
        if "$" in line
    ]
    assert not stray, f"README contains `$`, which re-pairs KaTeX: {stray}"


# ---------------------------------------------------------------------------
# Licensing: AGPL and nothing else
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "document", ["README.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE",
                 "THIRD-PARTY-LICENSES.md"])
def test_the_document_set_is_present(document):
    """One missing is one the others link to and this repository does not have."""
    assert os.path.exists(os.path.join(REPO, document))


def test_there_is_no_commercial_tier_and_nothing_claims_there_is():
    """Argus withdrew its commercial licence because it could not be kept: the
    forecast runs on weights licensed for non-commercial use only. Tyche runs
    on the same weights and never had one to withdraw. A stray sentence
    offering to sell a licence would be offering something that does not
    exist, and a document nobody re-reads is exactly where such a sentence
    survives.
    """
    assert not os.path.exists(os.path.join(REPO, "COMMERCIAL-LICENSE.md"))
    for name in ("README.md", "CONTRIBUTING.md", "THIRD-PARTY-LICENSES.md",
                 ".github/release-body.md"):
        assert "COMMERCIAL-LICENSE.md" not in read(name), (
            f"{name} points at a document that does not exist")


def test_there_is_no_cla_and_nothing_asks_a_contributor_to_sign_one():
    """A CLA exists to let an owner relicense contributions commercially.

    With no commercial tier there is nothing to relicense *to*, so asking for
    one would be collecting a right nobody intends to use. A contribution is
    offered under the AGPL like everything else here.
    """
    assert not os.path.exists(os.path.join(REPO, "CLA.md"))
    for name in ("README.md", "CONTRIBUTING.md"):
        assert "CLA.md" not in read(name), f"{name} links a CLA that does not exist"


def test_the_readme_says_the_licence_is_agpl_and_only_that():
    # Whitespace-normalised: the README is hard-wrapped at 79 columns, so
    # every phrase long enough to be worth asserting on is liable to have a
    # newline through the middle of it.
    lowered = " ".join(read("README.md").lower().split())
    assert "agpl-3.0" in lowered
    assert "non c'è una licenza commerciale e non c'è un cla" in lowered


def test_the_agpl_text_is_not_edited():
    """The AGPL may be applied to a work, never rewritten.

    A reflowed copy is an edited copy: the licence's own header says changing
    it is not allowed, and GitHub stops recognising it.
    """
    licence = read("LICENSE")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in licence
    assert "Version 3, 19 November 2007" in licence
    assert "TERMS AND CONDITIONS" in licence

    # Deliberately not the word "price": the AGPL preamble uses it itself, in
    # "free as in freedom, not price". And matched on word boundaries, because
    # "VAT" is a substring of "private".
    for word in ("€", "VAT", "invoice", "per year", "subscription"):
        pattern = re.escape(word) if not word.isalpha() else rf"\b{word}\b"
        assert not re.search(pattern, licence, re.IGNORECASE), (
            f"LICENSE must stay verbatim AGPL, found {word!r}")


# ---------------------------------------------------------------------------
# The weights, which are the one restriction a reader must not miss
# ---------------------------------------------------------------------------

def test_the_weights_restriction_is_stated_where_a_user_meets_it():
    """Tyche's own code is free. The TimesFM 3.0 weights it downloads on first
    use are not: `timesfm-non-commercial-license-v1.0` allows non-commercial,
    non-production use only. That permission is not Tyche's to give, and
    burying it would be the most consequential omission in the project.
    """
    for name in ("README.md", "THIRD-PARTY-LICENSES.md", ".github/release-body.md"):
        lowered = read(name).lower()
        assert "timesfm-non-commercial-license-v1.0" in lowered, (
            f"{name} does not name the licence the weights are under")
        assert "non commerciale" in lowered or "non-commercial" in lowered, (
            f"{name} does not say what the licence excludes")


def test_the_documents_say_tyche_does_not_ship_the_weights():
    """It is the fact that keeps the AGPL distribution clean: the restricted
    artefact is fetched by the user at run time, not redistributed here.
    """
    lowered = read("THIRD-PARTY-LICENSES.md").lower()
    assert "scarica" in lowered or "download" in lowered
    assert "non è" in lowered or "not " in lowered


# ---------------------------------------------------------------------------
# The small things that get left behind
# ---------------------------------------------------------------------------

def test_a_reader_can_find_a_way_to_get_in_touch():
    assert CONTACT in read("README.md")


def test_the_contact_address_has_one_source_of_truth():
    """core/version.py holds it; the Markdown carries copies by necessity.

    Two addresses in one project is one of them being wrong, and the drift is
    invisible because nobody re-reads a footer.
    """
    import sys

    sys.path.insert(0, REPO)
    from core.version import CONTACT_EMAIL

    assert CONTACT_EMAIL == CONTACT
    # The domain is matched label by label so a sentence-ending full stop
    # stays out of it: `[\w.]+` at the end swallowed the one after
    # "gmail.com" and reported a second, nonexistent address.
    addresses = set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", read("README.md")))
    assert addresses <= {CONTACT}, f"README carries other addresses: {sorted(addresses)}"


def test_no_placeholder_survived_into_the_published_documents():
    """Matched on word boundaries, and the reason is Italian.

    "todo" is a substring of *metodo*, which this README says forty times; a
    plain `in` check reported the front page as full of unfinished markers.
    The same trap as "VAT" inside "private", one language over.
    """
    for name in ("README.md", "CONTRIBUTING.md", ".github/release-body.md"):
        lowered = read(name).lower()
        for placeholder in ("to be published", "tbd", "todo", "xxx", "your-domain"):
            found = re.search(rf"(?<![\w]){re.escape(placeholder)}(?![\w])", lowered)
            assert not found, f"{name}: placeholder left in: {placeholder!r}"


def test_the_inventory_document_is_reachable_from_the_readme():
    """A pointer to a file nobody links is a pointer to nothing."""
    assert "THIRD-PARTY-LICENSES.md" in read("README.md")
