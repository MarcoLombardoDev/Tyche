# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
tests/test_core.py — Tyche

Headless tests for everything outside gui/. They never touch the network: the
source parsers are exercised on fixtures, and the two that would download
something are tested through their parse functions instead.

Run with:  python -m pytest tests/ -q
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.archive import (  # noqa: E402
    NUMBER_MAX,
    ArchiveError,
    Draw,
    describe_archive,
    freshness,
    integrity_report,
    load_archive,
    merge_draws,
    preview_merge,
    repair_year_offset,
    save_archive,
    superenalotto_only,
)

# ─────────────────────────────────────────────────────────────
# Imports — a bare import failure is itself a regression
# ─────────────────────────────────────────────────────────────

def test_all_core_modules_import():
    import core.archive  # noqa: F401
    import core.data_manager  # noqa: F401
    import core.export  # noqa: F401
    import core.features  # noqa: F401
    import core.forecaster  # noqa: F401
    import core.predictor  # noqa: F401
    import core.randomness  # noqa: F401
    import core.selfcheck  # noqa: F401
    import core.sources  # noqa: F401
    import core.sources.estrazioni_it  # noqa: F401
    import core.statistics  # noqa: F401
    import core.stats_tests  # noqa: F401
    import core.validation  # noqa: F401


def test_declared_requirements_are_installed():
    """Every third-party module core/ imports must be in requirements.txt."""
    import numpy  # noqa: F401
    import requests  # noqa: F401


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def make_draw(day: int, contest: int, numbers=(1, 2, 3, 4, 5, 6), jolly=7, superstar=0, year=2010):
    return Draw(
        date=date(year, 1, 1) + timedelta(days=day),
        contest=contest, numbers=numbers, jolly=jolly, superstar=superstar,
    )


def random_archive(n: int, seed: int = 0) -> list[Draw]:
    """A synthetic archive of genuinely independent uniform draws.

    Used wherever a test needs the null hypothesis to be true by construction,
    so a failure means the code is wrong rather than that reality is odd.
    """
    rng = random.Random(seed)
    draws = []
    start = date(2000, 1, 1)
    for i in range(n):
        picked = rng.sample(range(1, NUMBER_MAX + 1), 7)
        draws.append(Draw(
            date=start + timedelta(days=3 * i),
            contest=i + 1,
            numbers=tuple(picked[:6]),
            jolly=picked[6],
            year=2000,
        ))
    return draws


# ─────────────────────────────────────────────────────────────
# Draw validation
# ─────────────────────────────────────────────────────────────

def test_numbers_are_stored_sorted():
    assert make_draw(0, 1, numbers=(9, 3, 71, 4, 5, 6)).numbers == (3, 4, 5, 6, 9, 71)


def test_draw_rejects_impossible_rows():
    with pytest.raises(ArchiveError):
        make_draw(0, 1, numbers=(1, 2, 3, 4, 5))          # five numbers
    with pytest.raises(ArchiveError):
        make_draw(0, 1, numbers=(1, 1, 3, 4, 5, 6))       # a repeat
    with pytest.raises(ArchiveError):
        make_draw(0, 1, numbers=(0, 2, 3, 4, 5, 6))       # 0 is not on the wheel
    with pytest.raises(ArchiveError):
        make_draw(0, 1, numbers=(1, 2, 3, 4, 5, 91))      # 91 is not either
    with pytest.raises(ArchiveError):
        make_draw(0, 1, jolly=3)                          # jolly repeats a main number
    with pytest.raises(ArchiveError):
        make_draw(0, 0)                                   # contest numbers start at 1


def test_superstar_may_repeat_a_main_number_but_jolly_may_not():
    """A separate drum for the SuperStar, the same one for the Jolly.

    163 rows of the real bulk archive have a SuperStar equal to one of the six.
    A validator that rejected them would silently discard four years of data.
    """
    assert make_draw(0, 1, superstar=3).superstar == 3
    with pytest.raises(ArchiveError):
        make_draw(0, 1, jolly=5)


def test_missing_jolly_is_allowed():
    """Zero means 'not on record'. Some archive pages do not print the Jolly."""
    assert make_draw(0, 1, jolly=0).jolly == 0


def test_draw_id_pairs_year_with_contest():
    assert make_draw(0, 8, year=2020).draw_id == "2020/8"


# ─────────────────────────────────────────────────────────────
# Archive I/O and merging
# ─────────────────────────────────────────────────────────────

def test_archive_round_trip(tmp_path):
    draws = random_archive(40)
    path = tmp_path / "a.csv"
    assert save_archive(path, draws) == 40
    reloaded = load_archive(path)
    assert [d.to_row()[:-1] for d in reloaded] == [d.to_row()[:-1] for d in draws]


def test_loading_a_missing_archive_is_empty_not_an_error(tmp_path):
    assert load_archive(tmp_path / "nope.csv") == []


def test_merge_keys_on_date_not_contest_id():
    """The bulk mirror gives nine real draws a duplicated contest id.

    Keying the merge on draw_id would delete one of each pair. This is the
    regression test for that, written from the defect that caused it.
    """
    a = make_draw(0, 1, numbers=(1, 2, 3, 4, 5, 6), year=2010)
    b = Draw(date=date(2011, 1, 1), contest=1, numbers=(10, 11, 12, 13, 14, 15),
             jolly=20, year=2010)          # same draw_id, different date
    assert a.draw_id == b.draw_id
    merged, added, _ = merge_draws([a], [b])
    assert added == 1
    assert len(merged) == 2


def test_merge_does_not_erase_a_known_superstar():
    with_ss = make_draw(0, 1, superstar=42)
    without = make_draw(0, 1, superstar=0)
    merged, _, _ = merge_draws([with_ss], [without])
    assert merged[0].superstar == 42


def test_superenalotto_only_drops_the_enalotto_era():
    old = Draw(date=date(1990, 5, 1), contest=1, numbers=(1, 2, 3, 4, 5, 6), jolly=7)
    new = Draw(date=date(1998, 5, 1), contest=1, numbers=(1, 2, 3, 4, 5, 6), jolly=7)
    assert superenalotto_only([old, new]) == [new]


def test_describe_archive_on_empty():
    assert describe_archive([])["count"] == 0


# ─────────────────────────────────────────────────────────────
# Integrity and repair
# ─────────────────────────────────────────────────────────────

def test_integrity_is_clean_on_a_well_formed_archive():
    assert integrity_report(random_archive(200)) == []


def test_integrity_finds_a_duplicated_date():
    draws = random_archive(20)
    clash = Draw(date=draws[5].date, contest=99, numbers=(11, 22, 33, 44, 55, 66),
                 jolly=1, year=draws[5].year)
    issues = integrity_report([*draws, clash])
    assert any(i.kind == "duplicate-date" and i.severity == "error" for i in issues)


def test_integrity_ignores_gaps_in_the_partial_first_and_last_years():
    """1997 legitimately starts at contest 87 and the current year is unfinished.

    Reporting either as a gap trains the reader to skip the section.
    """
    draws = [
        Draw(date=date(1997, 12, 3), contest=87, numbers=(1, 2, 3, 4, 5, 6), jolly=7),
        Draw(date=date(1998, 1, 3), contest=1, numbers=(1, 2, 3, 4, 5, 7), jolly=8),
        Draw(date=date(1998, 1, 7), contest=2, numbers=(1, 2, 3, 4, 5, 8), jolly=9),
        Draw(date=date(1999, 1, 6), contest=5, numbers=(1, 2, 3, 4, 5, 9), jolly=10),
    ]
    kinds = {i.kind for i in integrity_report(draws)}
    assert "contest-gap" not in kinds


def _mislabelled_block() -> list[Draw]:
    """1998 as the mirror has it: the real year, then nine 1999 draws labelled 1998.

    Contest 2 is given the *same date* in both blocks, reproducing the case no
    test on dates can resolve and only file position can.
    """
    real_1998 = [
        Draw(date=date(1998, 1, 3), contest=1, numbers=(1, 2, 3, 4, 5, 6), jolly=7, year=1998),
        Draw(date=date(1998, 1, 7), contest=2, numbers=(1, 2, 3, 4, 5, 8), jolly=9, year=1998),
    ]
    # 1999's own draws, on the Saturday/Wednesday schedule the game used. The
    # weekday test needs a real profile to work against: a target year holding
    # a single draw knows only one weekday and rejects every candidate.
    rest_1999 = [
        Draw(date=date(1999, 2, 3), contest=3, numbers=(10, 11, 12, 13, 14, 15), jolly=16),
        Draw(date=date(1999, 2, 6), contest=4, numbers=(40, 41, 42, 43, 44, 45), jolly=46),
        Draw(date=date(1999, 2, 10), contest=5, numbers=(50, 51, 52, 53, 54, 55), jolly=56),
        Draw(date=date(1999, 2, 13), contest=6, numbers=(60, 61, 62, 63, 64, 65), jolly=66),
    ]
    mislabelled = [
        # 1999-01-02 is a Saturday; 1999-01-03 a Sunday, so shifting the first
        # of these is unambiguous and anchors the block.
        Draw(date=date(1998, 1, 2), contest=1, numbers=(20, 21, 22, 23, 24, 25), jolly=26),
        Draw(date=date(1998, 1, 7), contest=2, numbers=(30, 31, 32, 33, 34, 35), jolly=36),
    ]
    return [*real_1998, *rest_1999, *mislabelled]


def test_repair_moves_the_whole_mislabelled_block():
    repaired, notes = repair_year_offset(_mislabelled_block())
    by_id = {d.draw_id: d for d in repaired}
    assert by_id["1999/1"].numbers == (20, 21, 22, 23, 24, 25)
    assert by_id["1999/2"].numbers == (30, 31, 32, 33, 34, 35)
    # And the genuine 1998 rows keep their own numbers.
    assert by_id["1998/1"].numbers == (1, 2, 3, 4, 5, 6)
    assert by_id["1998/2"].numbers == (1, 2, 3, 4, 5, 8)
    assert len(notes) == 2
    assert integrity_report(repaired) == []


def test_repair_resolves_equal_dates_by_position_not_by_date():
    """The bug this test exists for swapped two draws and passed every check.

    Choosing the "earlier date" agrees with file position for most pairs of
    the block and disagrees for exactly the pair that shares a date, so the
    wrong criterion produced a clean-looking archive with two draws exchanged.
    """
    repaired, _ = repair_year_offset(_mislabelled_block())
    moved = next(d for d in repaired if d.draw_id == "1999/2")
    assert moved.numbers == (30, 31, 32, 33, 34, 35)   # the later block's row


def test_repair_refuses_a_scattered_set():
    """Only a contiguous run of positions is a mislabelled block."""
    draws = [
        Draw(date=date(1998, 1, 3), contest=1, numbers=(1, 2, 3, 4, 5, 6), jolly=7, year=1998),
        Draw(date=date(1998, 1, 2), contest=1, numbers=(20, 21, 22, 23, 24, 25), jolly=26),
        Draw(date=date(1998, 6, 3), contest=50, numbers=(40, 41, 42, 43, 44, 45), jolly=46),
        Draw(date=date(1998, 6, 2), contest=50, numbers=(50, 51, 52, 53, 54, 55), jolly=56),
    ]
    repaired, notes = repair_year_offset(draws)
    assert len(repaired) == len(draws)
    assert any("scattered" in n or "not repairable" in n or "no anchor" in n for n in notes)


def test_repair_is_a_no_op_on_a_clean_archive():
    draws = random_archive(50)
    repaired, notes = repair_year_offset(draws)
    assert notes == []
    assert [d.to_row() for d in repaired] == [d.to_row() for d in draws]


# ─────────────────────────────────────────────────────────────
# Freshness and merge preview
# ─────────────────────────────────────────────────────────────

def _tue_thu_sat(weeks: int, start: date = date(2024, 1, 2)) -> list[Draw]:
    """An archive on the real Tuesday/Thursday/Saturday schedule."""
    draws, contest, day = [], 1, start
    while len(draws) < weeks * 3:
        if day.weekday() in (1, 3, 5):
            draws.append(Draw(date=day, contest=contest,
                              numbers=(1, 2, 3, 4, 5, 6), jolly=7))
            contest += 1
        day += timedelta(days=1)
    return draws


def test_freshness_of_an_empty_archive_says_so():
    state = freshness([])
    assert state.last_date is None and not state.stale


def test_freshness_reads_the_cadence_off_the_archive_itself():
    """Tuesday/Thursday/Saturday is 2, 2, 3 days: a mean of 2.33, not 2."""
    draws = _tue_thu_sat(20)
    state = freshness(draws, today=draws[-1].date)
    assert state.average_interval_days == pytest.approx(7 / 3, abs=0.05)
    assert state.days_behind == 0 and not state.stale


def test_freshness_counts_the_draws_missed_while_nobody_updated():
    draws = _tue_thu_sat(20)
    state = freshness(draws, today=draws[-1].date + timedelta(days=70))
    # 70 days at three draws a week is about 30. The median interval of 2.0
    # would say 35, which is the overcount the mean exists to avoid.
    assert 28 <= state.estimated_missing <= 32
    assert state.stale
    assert "mancano" in state.describe()


def test_freshness_tolerates_one_draw_and_duplicate_dates():
    """A degenerate archive must not divide by a zero-day interval."""
    single = [Draw(date=date(2024, 1, 2), contest=1, numbers=(1, 2, 3, 4, 5, 6), jolly=7)]
    assert freshness(single, today=date(2024, 1, 2)).average_interval_days >= 1.0
    twice = [*single, Draw(date=date(2024, 1, 2), contest=2,
                           numbers=(1, 2, 3, 4, 5, 8), jolly=9)]
    assert freshness(twice, today=date(2024, 1, 3)).average_interval_days >= 1.0


def test_preview_counts_what_a_merge_would_change():
    draws = random_archive(50)
    preview = preview_merge(draws[:40], draws)
    assert (preview.added, preview.updated, preview.unchanged) == (10, 0, 40)
    assert preview.first_new == draws[40].date
    assert preview.last_new == draws[-1].date
    assert preview.safe


def test_preview_flags_a_row_that_contradicts_a_stored_draw():
    """The signature of a mis-parse, and the reason the scraper asks first."""
    draws = random_archive(20)
    bad = Draw(date=draws[5].date, contest=draws[5].contest,
               numbers=(11, 22, 33, 44, 55, 66), jolly=1, year=draws[5].year)
    preview = preview_merge(draws, [bad])
    assert len(preview.conflicts) == 1
    assert not preview.safe
    assert "contraddicono" in preview.describe()


def test_preview_reports_integrity_errors_the_merge_would_introduce():
    draws = random_archive(30)
    clash = Draw(date=date(1999, 5, 5), contest=draws[0].contest,
                 numbers=(7, 8, 9, 10, 11, 12), jolly=13, year=draws[0].year)
    preview = preview_merge(draws, [clash])
    assert any(i.severity == "error" for i in preview.new_issues)
    assert not preview.safe


def test_preview_of_an_identical_fetch_changes_nothing():
    draws = random_archive(25)
    preview = preview_merge(draws, draws)
    assert (preview.added, preview.updated) == (0, 0)
    assert preview.safe
    assert "Niente di nuovo" in preview.describe()


# ─────────────────────────────────────────────────────────────
# Source parsers
# ─────────────────────────────────────────────────────────────

BULK_SAMPLE = """\
16,30,47,52,76,90,51,0,1,9,1,1961
2,29,36,72,82,90,71,0,1,3,1,1998
"08","10","43","52","60","83","84","61","150","14","12","2019"
3,10,25,34,58,88,55,0,9,29,2,1991
"""


def test_bulk_parser_reads_quoted_and_bare_rows_and_skips_impossible_dates():
    from core.sources.bulk_archive import parse_bulk_csv

    draws = parse_bulk_csv(BULK_SAMPLE)
    assert len(draws) == 3                       # 29 February 1991 never existed
    assert draws[-1].numbers == (8, 10, 43, 52, 60, 83)
    assert draws[-1].superstar == 61


def test_bulk_parser_raises_rather_than_returning_nothing():
    """An error page parses to zero draws, which must not read as 'up to date'."""
    from core.sources.base import SourceError
    from core.sources.bulk_archive import parse_bulk_csv

    with pytest.raises(SourceError):
        parse_bulk_csv("<html><body>404</body></html>")


HTML_SAMPLE = """
<table class="whatever">
  <tr><th>Concorso</th><th>Data</th><th>Combinazione</th><th>Jolly</th><th>SuperStar</th></tr>
  <tr>
    <td>47</td><td>04/01/2020</td>
    <td><span>3</span><span>17</span><span>29</span><span>44</span><span>61</span><span>80</span></td>
    <td>12</td><td>55</td>
  </tr>
  <tr>
    <td>48</td><td>07/01/2020</td>
    <td>1 5 12 33 44 78</td><td>90</td><td>2</td>
  </tr>
  <tr><td>nav</td><td>no date here</td><td>1 2 3</td></tr>
</table>
"""


def test_html_parser_reads_a_table_without_knowing_its_classes():
    from core.sources.html_table import parse_draw_table

    draws = parse_draw_table(HTML_SAMPLE, expect_year=2020)
    assert len(draws) == 2
    assert draws[0].numbers == (3, 17, 29, 44, 61, 80)
    assert draws[0].jolly == 12 and draws[0].superstar == 55
    assert draws[1].numbers == (1, 5, 12, 33, 44, 78)


def test_html_parser_does_not_mistake_the_contest_number_for_a_ball():
    """Contest 47 sits before the date and must not enter the combination."""
    from core.sources.html_table import parse_draw_table

    draws = parse_draw_table(HTML_SAMPLE, expect_year=2020)
    assert 47 not in draws[0].numbers
    assert draws[0].contest == 47


def test_html_parser_does_not_concatenate_adjacent_ball_elements():
    """``<span>1</span><span>5</span>`` is 1 and 5, never 15."""
    from core.sources.html_table import parse_draw_table

    html = (
        "<table><tr><td>1</td><td>04/01/2020</td>"
        "<td><b>1</b><b>5</b><b>12</b><b>33</b><b>44</b><b>78</b></td></tr></table>"
    )
    assert parse_draw_table(html, expect_year=2020)[0].numbers == (1, 5, 12, 33, 44, 78)


# The export from estrazioni.it, which is the archive Tyche actually runs on.
# Semicolon-separated, UTF-8 with a BOM, dd/mm/yyyy, zero-padded numbers, and a
# CONCORSO column that the site stopped filling in from 2014 onwards.
LABELLED_SAMPLE = (
    "\ufeffDATA;CONCORSO;N1;N2;N3;N4;N5;N6;JOLLY;SUPERSTAR\n"
    "03/09/2026;;08;11;15;60;68;76;09;90\n"
    "01/09/2026;;42;47;59;64;67;71;88;75\n"
    "03/12/1997;87;20;36;39;41;72;76;88;00\n"
)


def test_labelled_parser_reads_the_estrazioni_export():
    from core.sources.local_file import parse_any

    draws = sorted(parse_any(LABELLED_SAMPLE), key=lambda d: d.date)
    assert len(draws) == 3
    assert draws[0].date == date(1997, 12, 3)
    assert draws[0].numbers == (20, 36, 39, 41, 72, 76)
    assert draws[-1].numbers == (8, 11, 15, 60, 68, 76)
    assert draws[-1].jolly == 9 and draws[-1].superstar == 90


def test_labelled_parser_does_not_eat_a_contest_number_that_follows_the_date():
    """The bug this parser exists for.

    ``03/12/1997;87;20;36;39;41;72;76;88;00`` — the contest number comes
    *after* the date, and 87 is a perfectly good SuperEnalotto number, so the
    positional line scan read the draw as 20 36 39 41 72 87 with a Jolly of
    76. Every value plausible, nothing raised, and every row carrying a
    contest number silently wrong.
    """
    from core.sources.local_file import parse_any

    draw = next(d for d in parse_any(LABELLED_SAMPLE) if d.date == date(1997, 12, 3))
    assert 87 not in draw.numbers
    assert draw.contest == 87
    assert draw.jolly == 88


def test_labelled_parser_beats_the_positional_scan_on_the_same_text():
    """Proof the ordering in parse_any is what makes the difference."""
    from core.sources.local_file import _parse_freeform, parse_any

    positional = next(
        d for d in _parse_freeform(LABELLED_SAMPLE, "x") if d.date == date(1997, 12, 3)
    )
    labelled = next(d for d in parse_any(LABELLED_SAMPLE) if d.date == date(1997, 12, 3))
    assert 87 in positional.numbers      # the wrong answer, still reachable
    assert 87 not in labelled.numbers    # and the right one wins, because it is tried first


def test_labelled_parser_fills_a_missing_contest_number_by_ordinal():
    """estrazioni.it leaves CONCORSO empty from 2014; 2,008 of its rows have it."""
    from core.sources.local_file import parse_any

    text = (
        "DATA;CONCORSO;N1;N2;N3;N4;N5;N6;JOLLY;SUPERSTAR\n"
        "07/01/2026;;01;02;03;04;05;06;07;08\n"
        "02/01/2026;;10;11;12;13;14;15;16;17\n"
    )
    draws = sorted(parse_any(text), key=lambda d: d.date)
    assert [d.contest for d in draws] == [1, 2]


def test_labelled_parser_handles_comma_and_tab_delimiters():
    from core.sources.local_file import parse_any

    for delimiter in (",", "\t"):
        text = delimiter.join(
            ["DATA", "CONCORSO", "N1", "N2", "N3", "N4", "N5", "N6", "JOLLY", "SUPERSTAR"]
        ) + "\n" + delimiter.join(
            ["03/09/2026", "141", "08", "11", "15", "60", "68", "76", "09", "90"]
        ) + "\n"
        assert parse_any(text)[0].numbers == (8, 11, 15, 60, 68, 76)


def test_labelled_parser_refuses_a_header_it_cannot_map():
    from core.sources.base import SourceError
    from core.sources.local_file import _parse_labelled

    with pytest.raises(SourceError):
        _parse_labelled("A;B;C;D;E;F;G;H\n1;2;3;4;5;6;7;8\n", "x")


def test_local_file_parser_sniffs_all_three_layouts(tmp_path):
    from core.sources.local_file import parse_any

    canonical = tmp_path / "c.csv"
    save_archive(canonical, random_archive(5))
    assert len(parse_any(canonical.read_text())) == 5
    assert len(parse_any(BULK_SAMPLE)) == 3
    freeform = "concorso 12; 04/01/2020; 3 17 29 44 61 80; jolly 12\nrubbish line\n"
    assert parse_any(freeform)[0].numbers == (3, 17, 29, 44, 61, 80)


def test_local_file_parser_raises_on_an_unrecognisable_file():
    from core.sources.base import SourceError
    from core.sources.local_file import parse_any

    with pytest.raises(SourceError):
        parse_any("this file contains no draws at all\n")


def test_network_failures_are_reported_in_one_short_clause():
    """Four hosts times 250 characters of nested requests exception is a
    sentence nobody reads to the end."""
    import requests

    from core.sources.base import _reason

    assert _reason(requests.exceptions.ProxyError("x" * 300)) == (
        "blocked or unreachable through the proxy"
    )
    assert _reason(requests.exceptions.ConnectTimeout("x" * 300)) == "timed out"
    assert _reason(requests.exceptions.ConnectionError("x" * 300)) == "could not connect"
    assert len(_reason(ValueError("y" * 300))) <= 120


def test_scraper_puts_the_configured_template_first_and_does_not_repeat_it():
    from core.sources.html_table import DEFAULT_URL_TEMPLATE, HtmlTableSource

    source = HtmlTableSource(DEFAULT_URL_TEMPLATE, [2024])
    assert source.templates[0] == DEFAULT_URL_TEMPLATE
    assert source.templates.count(DEFAULT_URL_TEMPLATE) == 1

    custom = HtmlTableSource("https://example.invalid/{year}", [2024])
    assert custom.templates[0] == "https://example.invalid/{year}"
    assert DEFAULT_URL_TEMPLATE in custom.templates


def test_scraper_falls_through_to_the_first_host_that_answers(monkeypatch):
    """One unreachable host must not be the end of the attempt."""
    import core.sources.html_table as ht

    served = {"https://good.invalid/2024": HTML_SAMPLE.replace("2020", "2024")}

    def fake_get(url, timeout=30):
        if url not in served:
            raise ht.SourceError(f"{url}: HTTP 403")
        return served[url].encode()

    monkeypatch.setattr(ht, "http_get", fake_get)
    source = ht.HtmlTableSource(
        "https://bad.invalid/{year}", [2024],
        fallbacks=("https://alsobad.invalid/{year}", "https://good.invalid/{year}"),
    )
    draws = source.fetch()
    assert len(draws) == 2
    assert all("good.invalid" in d.source for d in draws)


def test_scraper_reports_every_host_it_tried_when_all_of_them_fail(monkeypatch):
    import core.sources.html_table as ht

    monkeypatch.setattr(ht, "http_get", lambda url, timeout=30: b"<html>nope</html>")
    source = ht.HtmlTableSource(
        "https://a.invalid/{year}", [2024], fallbacks=("https://b.invalid/{year}",)
    )
    with pytest.raises(ht.SourceError) as caught:
        source.fetch()
    assert "a.invalid" in str(caught.value) and "b.invalid" in str(caught.value)


def test_scraper_saves_the_page_when_asked(tmp_path, monkeypatch):
    """The parser cannot be fixed from a description of what went wrong."""
    import core.sources.html_table as ht

    monkeypatch.setattr(
        ht, "http_get", lambda url, timeout=30: HTML_SAMPLE.replace("2020", "2024").encode()
    )
    ht.HtmlTableSource(
        "https://saved.invalid/{year}", [2024], fallbacks=(), debug_dir=tmp_path
    ).fetch()
    saved = list(tmp_path.glob("*.html"))
    assert [p.name for p in saved] == ["saved.invalid-2024.html"]
    assert "Concorso" in saved[0].read_text()


def test_estrazioni_source_parses_the_export_with_the_shared_parser(monkeypatch):
    """The downloaded file and a hand-downloaded one must not take two paths."""
    import core.sources.estrazioni_it as source_module

    payload = (LABELLED_SAMPLE * 3000).encode()      # comfortably over the size floor
    monkeypatch.setattr(source_module, "http_get", lambda url, timeout=30: payload)
    draws = source_module.EstrazioniItSource().fetch()
    assert draws
    assert all(d.source == "estrazioni.it" for d in draws)


def test_estrazioni_source_rejects_a_short_error_page_that_returned_200():
    """These sites answer a bad query with a 200 and a courtesy page."""
    import core.sources.estrazioni_it as source_module

    class Stub(source_module.EstrazioniItSource):
        pass

    original = source_module.http_get
    source_module.http_get = lambda url, timeout=30: b"<html>not found</html>"
    try:
        with pytest.raises(source_module.SourceError, match="troppo pochi"):
            Stub().fetch()
    finally:
        source_module.http_get = original


def test_estrazioni_source_falls_through_its_candidate_urls(monkeypatch):
    """The download URL is inferred, so a wrong first guess must not be fatal."""
    import core.sources.estrazioni_it as source_module

    good = source_module.DOWNLOAD_URLS[-1]
    payload = (LABELLED_SAMPLE * 3000).encode()

    def fake_get(url, timeout=30):
        if url != good:
            raise source_module.SourceError(f"{url}: HTTP 404")
        return payload

    monkeypatch.setattr(source_module, "http_get", fake_get)
    assert source_module.EstrazioniItSource().fetch()


# ─────────────────────────────────────────────────────────────
# Statistics primitives
# ─────────────────────────────────────────────────────────────

def test_chi2_survival_matches_textbook_critical_values():
    from core.stats_tests import chi2_sf

    assert chi2_sf(3.841458820694124, 1) == pytest.approx(0.05, abs=1e-10)
    assert chi2_sf(11.070497693516351, 5) == pytest.approx(0.05, abs=1e-10)
    assert chi2_sf(0.0, 3) == 1.0


def test_normal_survival_matches_textbook_values():
    from core.stats_tests import normal_sf, two_sided_normal_p

    assert normal_sf(1.959963984540054) == pytest.approx(0.025, abs=1e-12)
    assert two_sided_normal_p(1.959963984540054) == pytest.approx(0.05, abs=1e-12)


def test_hypergeometric_is_a_distribution_with_the_right_mean():
    from core.stats_tests import hypergeom_moments, hypergeom_pmf

    pmf = [hypergeom_pmf(90, 6, 6, k) for k in range(7)]
    assert sum(pmf) == pytest.approx(1.0, abs=1e-12)
    mean, variance = hypergeom_moments(90, 6, 6)
    assert mean == pytest.approx(0.4)
    assert sum(k * p for k, p in enumerate(pmf)) == pytest.approx(mean, abs=1e-12)
    second = sum(k * k * p for k, p in enumerate(pmf))
    assert second - mean ** 2 == pytest.approx(variance, abs=1e-12)


def test_chi_square_pools_small_bins_and_reports_the_dof_it_used():
    from core.stats_tests import chi_square_goodness_of_fit

    _, dof, _ = chi_square_goodness_of_fit([50, 50, 1, 0], [50, 50, 1, 0.5])
    assert dof == 1          # the two tiny bins were pooled into their neighbour


# ─────────────────────────────────────────────────────────────
# Features
# ─────────────────────────────────────────────────────────────

def test_presence_matrix_has_six_ones_per_column():
    from core.features import presence_matrix

    matrix = presence_matrix(random_archive(50))
    assert matrix.shape == (90, 50)
    assert np.all(matrix.sum(axis=0) == 6)


def test_rolling_frequency_starts_at_a_real_frequency():
    """No zero-padded ramp: a model fed one learns it and looks skilful."""
    from core.features import presence_matrix, rolling_frequency

    frequency = rolling_frequency(presence_matrix(random_archive(300)), window=50)
    assert frequency[:, 0].sum() == pytest.approx(6.0)     # first column: 6 of 90 at 1.0
    assert frequency.mean() == pytest.approx(6 / 90, abs=1e-6)


def test_gap_matrix_does_not_leak_the_target_draw():
    """Column t is what a player saw *before* draw t; the reset lands at t+1."""
    from core.features import gap_matrix, presence_matrix

    draws = random_archive(60)
    presence = presence_matrix(draws)
    gaps = gap_matrix(presence)
    for t in range(1, 60):
        drawn_now = np.nonzero(presence[:, t])[0]
        # If the reset leaked, every number drawn at t would read 0 at t.
        assert not np.all(gaps[drawn_now, t] == 0)


def test_current_gaps_distinguishes_never_seen_from_just_seen():
    from core.features import current_gaps

    draws = [Draw(date=date(2020, 1, 1), contest=1, numbers=(1, 2, 3, 4, 5, 6), jolly=7)]
    gaps = current_gaps(draws)
    assert gaps[1] == 0
    assert gaps[90] == 1        # never drawn in a one-draw archive


def test_decade_profile_sums_to_six_and_has_nine_bands():
    from core.features import decade_profile

    profile = decade_profile(Draw(date=date(2020, 1, 1), contest=1,
                                  numbers=(1, 10, 11, 80, 85, 90), jolly=2))
    assert len(profile) == 9 and sum(profile) == 6
    assert profile[0] == 2      # 1 and 10 — the band is 1–10, not 1–9
    assert profile[7] == 1      # 80 closes the 71–80 band
    assert profile[8] == 2      # 85 and 90


# ─────────────────────────────────────────────────────────────
# Randomness tests
# ─────────────────────────────────────────────────────────────

def test_independence_tests_pass_on_a_genuinely_random_archive():
    """The null is true by construction here, so the tests must not reject it.

    Five tests at 5% would reject a true null about 23% of the time by chance,
    so the seed is fixed rather than the threshold loosened — a flaky test that
    says "randomness is not random" once a week teaches nobody anything.
    """
    from core.randomness import run_all

    results = run_all(random_archive(2000, seed=7))
    assert [r.significant for r in results] == [False] * 5


def test_independence_tests_detect_a_rigged_archive():
    """A biased archive must fail, or the tests are decoration.

    Here numbers 1-12 are drawn far more often than the rest, which is the
    "hot numbers" claim made true. The uniformity test has to see it.
    """
    from core.randomness import uniformity_test

    rng = random.Random(3)
    draws = []
    for i in range(1200):
        picked = rng.sample(range(1, 13), 4) + rng.sample(range(13, 91), 3)
        draws.append(Draw(date=date(2000, 1, 1) + timedelta(days=i), contest=i + 1,
                          numbers=tuple(picked[:6]), jolly=picked[6]))
    assert uniformity_test(draws).significant


def test_summarise_says_nothing_is_exploitable_when_nothing_is():
    from core.randomness import run_all, summarise

    assert "struttura sfruttabile" in summarise(run_all(random_archive(1500, seed=11)))


# ─────────────────────────────────────────────────────────────
# Prediction
# ─────────────────────────────────────────────────────────────

def test_category_odds_match_the_published_figures():
    """These are the operator's own numbers and they are exact combinatorics."""
    from core.predictor import category_odds

    odds = category_odds()
    assert odds["6"] == 622_614_630
    assert odds["5+1"] == 103_769_105
    assert odds["5"] == 1_250_230
    assert odds["4"] == 11_907
    assert odds["3"] == 327


def test_expected_hits_is_four_tenths():
    from core.predictor import expected_hits

    assert expected_hits() == pytest.approx(0.4)


def test_every_method_produces_six_distinct_playable_numbers():
    from core.predictor import METHODS, predict

    draws = random_archive(500)
    for method in METHODS:
        if method == "timesfm":
            continue
        prediction = predict(draws, method=method, combinations=3, seed=1)
        assert len(prediction.combinations) == 3
        for combination in prediction.combinations:
            assert len(set(combination)) == 6
            assert all(1 <= n <= 90 for n in combination)


def test_ranking_is_deterministic_when_scores_tie():
    """The presence representation forecasts near-identical values for all 90."""
    from core.predictor import rank_numbers

    flat = dict.fromkeys(range(1, 91), 0.5)
    assert rank_numbers(flat) == list(range(1, 91))


def test_combinations_slide_down_the_ranking():
    from core.predictor import build_combinations

    combos = build_combinations(list(range(1, 91)), count=3, size=6)
    assert combos[0] == (1, 2, 3, 4, 5, 6)
    assert combos[1] == (2, 3, 4, 5, 6, 7)
    assert combos[2] == (3, 4, 5, 6, 7, 8)


def test_timesfm_method_refuses_without_a_forecaster():
    from core.predictor import predict

    with pytest.raises(ValueError):
        predict(random_archive(300), method="timesfm")


# ─────────────────────────────────────────────────────────────
# Validation harness
# ─────────────────────────────────────────────────────────────

def test_walk_forward_scores_baselines_at_chance_on_a_random_archive():
    from core.validation import walk_forward

    report = walk_forward(random_archive(900, seed=5), n_draws=500, min_history=200)
    for result in report.results:
        # Two standard errors on 500 draws is about 0.053 hits per draw.
        assert abs(result.mean_hits - 0.4) < 0.12
        assert result.draws_scored == 500


class _OracleForecaster:
    """A forecaster that cheats, to prove the harness would notice if it could.

    It is handed only the history, like every other method, but it knows the
    archive and uses ``len(history)`` to look up the draw it is being asked to
    predict. If :func:`core.validation.walk_forward` scored it at anything
    other than a perfect 6.0, the harness could not detect skill and none of
    its "no better than chance" verdicts would mean anything.
    """

    def __init__(self, draws):
        self._draws = draws

    def score_numbers(self, history, progress=None):
        actual = set(self._draws[len(history)].numbers)
        return {n: (1.0 if n in actual else 0.0) for n in range(1, 91)}


def test_walk_forward_would_detect_a_method_that_actually_worked():
    from core.validation import walk_forward

    draws = random_archive(400, seed=9)
    report = walk_forward(
        draws, methods=["timesfm"], n_draws=100, min_history=200,
        forecaster=_OracleForecaster(draws),
    )
    result = report.results[0]
    assert result.mean_hits == 6.0
    assert result.p_value < 1e-12
    assert "lo superano" in report.verdict()


def test_walk_forward_shows_no_look_ahead_in_the_real_methods():
    """The baselines see ``draws[:i]``; an off-by-one would show up as skill."""
    from core.validation import walk_forward

    report = walk_forward(random_archive(700, seed=13), n_draws=400, min_history=200)
    assert all(r.mean_hits < 1.0 for r in report.results)


def test_walk_forward_rejects_an_unknown_method():
    from core.validation import walk_forward

    with pytest.raises(ValueError):
        walk_forward(random_archive(300), methods=["astrology"], n_draws=50)


def test_walk_forward_refuses_when_there_is_no_history_to_spare():
    from core.validation import walk_forward

    with pytest.raises(ValueError):
        walk_forward(random_archive(50), n_draws=10, min_history=200)


# ─────────────────────────────────────────────────────────────
# The bundle self-check
# ─────────────────────────────────────────────────────────────

def test_the_headless_self_checks_pass():
    """Everything --self-check does that does not need a display.

    These run in the core suite because they are the checks a frozen bundle
    fails when numpy's compiled extensions or sqlite3 were not collected, and
    that has nothing to do with having a screen.
    """
    from core.selfcheck import _check_analysis, _check_export, _check_persistence

    for check in (_check_analysis, _check_persistence, _check_export):
        ok, message = check()
        assert ok, message


def test_the_self_check_reports_whether_timesfm_is_bundled_rather_than_failing():
    """A bundle without torch is a smaller working program, not a broken one."""
    from core.selfcheck import _check_timesfm

    ok, message = _check_timesfm()
    assert ok
    assert "timesfm:" in message


def test_the_self_check_fixture_builds_valid_draws():
    """It failed on its own fixture once: a fixed Jolly beside six random
    numbers eventually collides with one of them, and Draw rejects that."""
    from core.selfcheck import _check_export

    for _ in range(5):
        ok, message = _check_export()
        assert ok, message


# ─────────────────────────────────────────────────────────────
# SQLite export
# ─────────────────────────────────────────────────────────────

def test_sqlite_export_carries_every_draw_and_every_pick(tmp_path):
    import sqlite3

    from core.export import export_sqlite

    draws = random_archive(120)
    path = export_sqlite(draws, tmp_path / "t.db")
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT count(*) FROM draws").fetchone()[0] == 120
        # Six numbers per draw, denormalised into picks for GROUP BY queries.
        assert connection.execute("SELECT count(*) FROM picks").fetchone()[0] == 720
        assert connection.execute("SELECT count(*) FROM number_stats").fetchone()[0] == 90
        total = connection.execute(
            "SELECT total FROM draws ORDER BY date LIMIT 1"
        ).fetchone()[0]
        assert total == sum(draws[0].numbers)
    finally:
        connection.close()


def test_sqlite_export_replaces_an_existing_file(tmp_path):
    """It is a snapshot, not a store: re-exporting must not append."""
    import sqlite3

    from core.export import export_sqlite

    path = tmp_path / "t.db"
    export_sqlite(random_archive(50), path)
    export_sqlite(random_archive(30, seed=2), path)
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT count(*) FROM draws").fetchone()[0] == 30
    finally:
        connection.close()


# ─────────────────────────────────────────────────────────────
# The command line
# ─────────────────────────────────────────────────────────────

def test_update_scrapes_from_the_bootstrap_year_not_from_today(tmp_path, monkeypatch):
    """A fresh install must not leave 2020–today to a second invocation.

    The bootstrap has run but has not been written yet, so reading the last
    known year off the stored archive alone gives the current year and scrapes
    one year instead of six.
    """
    import core.data_manager as dm
    import core.sources as sources
    import main as cli

    monkeypatch.setattr(dm, "ARCHIVE_PATH", tmp_path / "empty.csv")
    requested: dict = {}

    class FakeExport:
        """estrazioni.it down, which is what puts the other two in play."""

        def fetch(self, progress=None):
            raise sources.SourceError("blocked")

    class FakeBulk:
        def __init__(self, url, repair_labels=True):
            pass

        def fetch(self, progress=None):
            return [
                Draw(date=date(2020, 1, 21), contest=9,
                     numbers=(6, 32, 46, 53, 70, 75), jolly=62),
            ]

    class FakeHtml:
        def __init__(self, template, years, **kwargs):
            requested["years"] = years

        def fetch(self, progress=None):
            raise sources.SourceError("blocked, as it is everywhere this was written")

    monkeypatch.setattr(sources, "EstrazioniItSource", FakeExport)
    monkeypatch.setattr(sources, "BulkArchiveSource", FakeBulk)
    monkeypatch.setattr(sources, "HtmlTableSource", FakeHtml)

    cli._run_update(write=False)
    assert requested["years"][0] == 2020
    assert requested["years"][-1] == date.today().year


def test_update_stops_after_the_export_and_bothers_nobody_else(tmp_path, monkeypatch):
    """The estrazioni.it export is the whole archive; nothing else can add to it."""
    import core.data_manager as dm
    import core.sources as sources
    import main as cli

    monkeypatch.setattr(dm, "ARCHIVE_PATH", tmp_path / "empty.csv")
    touched: list[str] = []

    class FakeExport:
        def fetch(self, progress=None):
            touched.append("export")
            return random_archive(30)

    class ShouldNotRun:
        def __init__(self, *a, **k):
            touched.append("other")

        def fetch(self, progress=None):
            touched.append("other")
            return []

    monkeypatch.setattr(sources, "EstrazioniItSource", FakeExport)
    monkeypatch.setattr(sources, "BulkArchiveSource", ShouldNotRun)
    monkeypatch.setattr(sources, "HtmlTableSource", ShouldNotRun)

    assert cli._run_update(write=False) == 0
    assert touched == ["export"]


def test_update_writes_nothing_without_yes(tmp_path, monkeypatch):
    import core.data_manager as dm
    import main as cli

    archive = tmp_path / "a.csv"
    monkeypatch.setattr(dm, "ARCHIVE_PATH", archive)
    assert cli._apply(random_archive(20), write=False) == 0
    assert not archive.exists()


def test_apply_refuses_to_write_a_contradicting_import(tmp_path, monkeypatch, capsys):
    """--yes is permission to write a clean import, not to overwrite good rows."""
    import core.data_manager as dm
    import main as cli

    archive = tmp_path / "a.csv"
    draws = random_archive(20)
    save_archive(archive, draws)
    monkeypatch.setattr(dm, "ARCHIVE_PATH", archive)

    bad = Draw(date=draws[3].date, contest=draws[3].contest,
               numbers=(11, 22, 33, 44, 55, 66), jolly=1, year=draws[3].year)
    assert cli._apply([bad], write=True) == 1
    assert "Scrittura rifiutata" in capsys.readouterr().out
    assert [d.to_row() for d in load_archive(archive)] == [d.to_row() for d in draws]


def test_apply_writes_a_clean_import(tmp_path, monkeypatch):
    import core.data_manager as dm
    import main as cli

    archive = tmp_path / "a.csv"
    draws = random_archive(30)
    save_archive(archive, draws[:20])
    monkeypatch.setattr(dm, "ARCHIVE_PATH", archive)
    assert cli._apply(draws, write=True) == 0
    assert len(load_archive(archive)) == 30


# ─────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────

def test_settings_template_matches_the_code_defaults():
    """Argus's two copies of its defaults drifted; Tyche's cannot.

    ``config/settings.template.json`` is generated from DEFAULT_SETTINGS, so
    if this fails, run ``python -c "from core.data_manager import
    write_settings_template as w; w()"`` and commit the result.
    """
    from core.data_manager import DEFAULT_SETTINGS, SETTINGS_TEMPLATE_PATH

    committed = json.loads(SETTINGS_TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert committed == DEFAULT_SETTINGS


def test_the_template_carries_no_credentials():
    from core.data_manager import SETTINGS_TEMPLATE_PATH

    committed = json.loads(SETTINGS_TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert committed["hf_token"] == ""


def test_settings_round_trip(tmp_path, monkeypatch):
    import core.data_manager as dm

    monkeypatch.setattr(dm, "SETTINGS_PATH", tmp_path / "settings.json")
    settings = dm.load_settings()
    settings["context_length"] = 512
    dm.save_settings(settings)
    assert dm.load_settings()["context_length"] == 512


def test_a_0_1_0_settings_file_is_read_with_the_new_names(tmp_path, monkeypatch):
    """The English names 0.1.0 wrote must not reach build_context.

    An unmapped ``"frequency"`` raises "rappresentazione sconosciuta" the first
    time a forecast is asked for, which is a long way from where the stale
    file is.
    """
    import json

    import core.data_manager as dm
    from core.features import build_context
    from core.predictor import METHODS

    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"representation": "frequency",
                    "validation_baselines": ["random", "frequency", "gap"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(dm, "SETTINGS_PATH", path)

    settings = dm.load_settings()
    assert settings["representation"] == "frequenza"
    assert settings["validation_baselines"] == ["casuale", "frequenza", "ritardo"]
    # Not just renamed — renamed to something the rest of the program accepts.
    build_context(random_archive(60), representation=settings["representation"])
    assert set(settings["validation_baselines"]) <= set(METHODS)


def test_prediction_log_round_trip(tmp_path, monkeypatch):
    import core.data_manager as dm

    monkeypatch.setattr(dm, "PREDICTION_LOG_PATH", tmp_path / "log.jsonl")
    dm.log_prediction({"method": "frequency", "combinations": [[1, 2, 3, 4, 5, 6]]})
    dm.log_prediction({"method": "random", "combinations": [[7, 8, 9, 10, 11, 12]]})
    entries = dm.load_prediction_log()
    assert [e["method"] for e in entries] == ["frequency", "random"]
    assert all("logged_at" in e for e in entries)


# ─────────────────────────────────────────────────────────────
# Forecaster — everything that does not need the weights
# ─────────────────────────────────────────────────────────────

def test_forecaster_reports_the_chunking_it_will_do():
    """Ninety variates against TimesFM's 32-per-pass limit is three chunks."""
    from core.forecaster import TimesFMForecaster

    assert "3 blocchi di attenzione" in TimesFMForecaster().describe()


def test_forecaster_fails_soft_when_timesfm_is_absent():
    """A missing model must not be an exception on the GUI's worker thread."""
    from core.forecaster import TimesFMForecaster

    forecaster = TimesFMForecaster()
    if forecaster.load_model(lambda *_: None):
        pytest.skip("timesfm is installed in this environment")
    assert forecaster.loaded is False


def test_scoring_without_a_loaded_model_raises_clearly():
    from core.forecaster import ForecasterUnavailable, TimesFMForecaster

    with pytest.raises(ForecasterUnavailable):
        TimesFMForecaster().score_numbers(random_archive(400))


def test_scoring_refuses_a_history_too_short_to_mean_anything():
    from core.forecaster import ForecasterUnavailable, TimesFMForecaster

    forecaster = TimesFMForecaster()
    forecaster._model = object()          # pretend it loaded
    with pytest.raises(ForecasterUnavailable, match="troppo poche"):
        forecaster.score_numbers(random_archive(10))


# ─────────────────────────────────────────────────────────────
# Rank scoring, and the blind spot it exists to cover
# ─────────────────────────────────────────────────────────────

def test_tied_numbers_share_the_group_mean_rank():
    """Otherwise the metric reads the tie-break instead of the method.

    frequenza scores ninety numbers on about fourteen distinct values, with
    tie groups up to seventeen wide, and rank_numbers breaks those ties by the
    number itself. Straight positional ranks would hand number 3 a better rank
    than number 80 every time they were level, and a rank statistic would
    report that convention as a preference for low numbers.
    """
    from core.scoring import mid_ranks

    scores = dict.fromkeys(range(1, 91), 0.0)
    scores[7] = 1.0                                    # one clear winner
    ranks = mid_ranks(scores)
    assert ranks[7] == 1.0
    # The other 89 share positions 2..90, so all of them sit at 46.0.
    assert {ranks[n] for n in range(1, 91) if n != 7} == {46.0}


def test_the_mean_of_the_mid_ranks_is_always_the_null_mean():
    """True whatever the ties are, which is what makes 45.5 the null."""
    from core.scoring import MEAN_RANK, mid_ranks

    for scores in (
        dict.fromkeys(range(1, 91), 0.0),
        {n: float(n) for n in range(1, 91)},
        {n: float(n % 3) for n in range(1, 91)},
        {n: random.Random(n).random() for n in range(1, 91)},
    ):
        ranks = mid_ranks(scores)
        assert abs(sum(ranks.values()) / 90 - MEAN_RANK) < 1e-9


def test_a_method_that_cannot_discriminate_has_no_null_variance():
    """It cannot deviate from chance, so it must not be credited with trying."""
    from core.scoring import mid_ranks, rank_null_variance

    flat = mid_ranks(dict.fromkeys(range(1, 91), 0.0))
    assert rank_null_variance(flat) == 0.0

    distinct = mid_ranks({n: float(n) for n in range(1, 91)})
    # Sampling six of ninety without replacement from ranks 1..90.
    expected = ((90 ** 2 - 1) / 12 / 6) * (84 / 89)
    assert abs(rank_null_variance(distinct) - expected) < 1e-9


def test_the_hit_count_is_blind_to_an_edge_below_the_top_six():
    """The reason core/scoring.py exists, asserted rather than described.

    The ``nascosto`` shape pushes the drawn numbers up the ranking but caps
    them below halfway, so the top six never change and the hit count cannot
    move by construction. Measured on the real archive its z-score is the
    identical number at every edge size. The rank statistic sees it.
    """
    from core.power import _KnownEdge
    from core.validation import walk_forward

    draws = random_archive(600, seed=11)
    hits_z = []
    # 0.60 is chosen so the cap is load-bearing: a number scored just under
    # 0.5 plus 0.6 would outrank every unnudged number, so without the cap the
    # hit count would jump and this test would fail. Checked by removing it.
    for size in (0.0, 0.20, 0.60):
        result = walk_forward(
            draws, methods=["timesfm"], n_draws=300,
            forecaster=_KnownEdge(draws, "nascosto", size),
        ).results[0]
        hits_z.append(round(result.z, 10))
        if size > 0:
            assert result.rank_z > 3, f"rank blind too at size {size}: z={result.rank_z}"

    assert len(set(hits_z)) == 1, f"the hit count moved, so the cap leaks: {hits_z}"


def test_the_hidden_edge_provably_never_reaches_the_top_six():
    """The invariant the shape claims, asserted directly rather than inferred.

    Stated as a property over every size rather than the few the test above
    happens to run, because "the hit count did not move" is also what a shape
    with no edge at all would produce.
    """
    from core.power import _KnownEdge
    from core.predictor import rank_numbers

    draws = random_archive(300, seed=15)
    for size in (0.1, 0.5, 0.9, 5.0):
        edge = _KnownEdge(draws, "nascosto", size)
        baseline = _KnownEdge(draws, "nascosto", 0.0)
        for i in range(200, 260):
            scores = edge.score_numbers(draws[:i])
            # Size zero leaves the same random stream untouched, so comparing
            # against it names exactly the numbers the edge moved. A drawn
            # number that started above 0.5 is not nudged at all and may reach
            # the top six on its own — that is chance, not the edge, and
            # counting it would make this test fail for the wrong reason.
            before = baseline.score_numbers(draws[:i])
            moved = {n for n in draws[i].numbers if scores[n] != before[n]}
            top_six = set(rank_numbers(scores)[:6])
            assert not (top_six & moved), (
                f"a nudged number reached the top six at size {size}"
            )
            assert all(scores[n] < 0.5 for n in moved)


def test_an_edge_at_the_top_is_seen_by_both_metrics():
    """The complement: where the hit count works, the rank statistic agrees."""
    from core.power import _KnownEdge
    from core.validation import walk_forward

    draws = random_archive(600, seed=12)
    result = walk_forward(
        draws, methods=["timesfm"], n_draws=300,
        forecaster=_KnownEdge(draws, "diffuso", 0.05),
    ).results[0]
    assert result.z > 3
    assert result.rank_z > 3


def test_a_known_edge_of_size_zero_is_indistinguishable_from_chance():
    """The control. Without it every other row of the calibration is noise."""
    from core.power import _KnownEdge
    from core.validation import walk_forward

    draws = random_archive(600, seed=13)
    result = walk_forward(
        draws, methods=["timesfm"], n_draws=300,
        forecaster=_KnownEdge(draws, "diffuso", 0.0),
    ).results[0]
    assert abs(result.z) < 3
    assert abs(result.rank_z) < 3


def test_a_perfect_oracle_tops_the_rank_statistic_too():
    """3.5 is the mean of ranks 1..6: every drawn number first."""
    from core.power import _KnownEdge
    from core.validation import walk_forward

    draws = random_archive(400, seed=14)
    result = walk_forward(
        draws, methods=["timesfm"], n_draws=100,
        forecaster=_KnownEdge(draws, "concentrato", 1.0),
    ).results[0]
    assert result.mean_hits == 6.0
    assert abs(result.mean_rank - 3.5) < 1e-9


def test_the_calibration_instruments_are_not_selectable_methods():
    """They cheat by construction, so nothing a user drives may reach them."""
    from core.predictor import METHODS

    for shape in ("concentrato", "diffuso", "nascosto"):
        assert shape not in METHODS


def test_an_unknown_edge_shape_is_refused():
    from core.power import _KnownEdge

    with pytest.raises(ValueError, match="forma sconosciuta"):
        _KnownEdge(random_archive(50), "inventata", 0.1)


# ─────────────────────────────────────────────────────────────
# Multiple testing
# ─────────────────────────────────────────────────────────────

def test_holm_adjustment_scales_by_the_remaining_tests():
    from core.randomness import holm_adjust

    # Smallest scaled by 3, next by 2, largest by 1.
    assert holm_adjust([0.01, 0.04, 0.05]) == pytest.approx([0.03, 0.08, 0.08])


def test_holm_adjustment_never_lowers_a_p_value():
    from core.randomness import holm_adjust

    raw = [0.001, 0.02, 0.3, 0.04, 0.9]
    for before, after in zip(raw, holm_adjust(raw), strict=True):
        assert after >= before
        assert after <= 1.0


def test_holm_adjustment_keeps_the_ordering():
    """A step-down procedure that inverted two p-values would be wrong."""
    from core.randomness import holm_adjust

    raw = [0.001, 0.049, 0.02, 0.5]
    adjusted = holm_adjust(raw)
    by_raw = sorted(range(len(raw)), key=lambda i: raw[i])
    ordered = [adjusted[i] for i in by_raw]
    assert ordered == sorted(ordered)


def test_the_summary_reports_the_family_wise_risk():
    """Five tests at 5% flag something 23% of the time. Say so with a number."""
    from core.randomness import run_all, summarise

    # A fair archive: nothing should flag, and the text says all five passed.
    text = summarise(run_all(random_archive(1200, seed=5)))
    assert "compatibili" in text or "Holm" in text


def test_holm_survives_the_sum_finding_on_a_planted_bias():
    """A real effect must not be corrected away, only a lucky one."""
    from core.randomness import holm_adjust

    # One overwhelming p-value among five ordinary ones stays significant.
    adjusted = holm_adjust([0.0002, 0.33, 0.64, 0.55, 0.29])
    assert adjusted[0] < 0.05
    assert all(a > 0.05 for a in adjusted[1:])


def test_every_setting_is_read_somewhere():
    """A setting nothing reads is a promise the program does not keep.

    Four of them had accumulated by 0.3.0. ``numbers_per_combination`` sat in
    the template at 6 while build_combinations took its size from a constant,
    so a user setting 7 would have seen no change and no error;
    ``auto_repair_labels`` was declared as an on/off switch over a repair that
    always ran; ``last_archive_update`` was never written; and
    ``validation_baselines`` was carried through load_settings and then
    ignored. Nothing failed, which is exactly the problem — the committed
    template is documentation, and it was describing a program that did not
    exist.

    This is a static check on purpose. It cannot tell whether a key is read
    *correctly*, only whether the name appears anywhere outside the module
    that declares it, which is the cheap half and the half that was missing.
    """
    from core.data_manager import DEFAULT_SETTINGS

    repo = Path(__file__).resolve().parent.parent
    sources = [repo / "main.py"]
    sources += sorted(repo.glob("core/**/*.py")) + sorted(repo.glob("gui/**/*.py"))
    # The module that declares them does not count as a reader.
    sources = [s for s in sources if s.name != "data_manager.py"]
    text = "\n".join(s.read_text(encoding="utf-8") for s in sources)

    unread = [
        key for key in DEFAULT_SETTINGS
        if f'"{key}"' not in text and f"'{key}'" not in text
    ]
    assert not unread, (
        "declared in DEFAULT_SETTINGS and shipped in the template, but nothing "
        f"outside core/data_manager.py reads: {', '.join(unread)}"
    )


def test_the_settings_panel_offers_every_setting_a_user_should_set():
    """The mirror of the test above: declared, read, but not reachable.

    Four keys are deliberately absent from the panel because their own tab
    owns them — listing them twice would give a user two places to set one
    thing and no rule about which wins.
    """
    from core.data_manager import DEFAULT_SETTINGS
    from gui.settings_panel import FIELDS

    # Set from the tab that uses them, and deliberately not repeated here:
    # two places to set one thing needs a rule about which wins, and there is
    # none. validation_draws is the exception — the panel and the Validate tab
    # edit the same key and the tab reads it back, so they agree.
    owned_elsewhere = {"prediction_method", "combinations", "validation_baselines"}
    shown = {key for key, *_ in FIELDS}
    assert shown | owned_elsewhere >= set(DEFAULT_SETTINGS)
    assert not (shown & owned_elsewhere), "a setting with two homes"


def test_the_bulk_source_can_be_told_not_to_repair():
    """The switch has to reach the code, not just the settings file."""
    from core.sources.bulk_archive import BulkArchiveSource

    assert BulkArchiveSource("http://example.invalid").repair_labels is True
    assert BulkArchiveSource(
        "http://example.invalid", repair_labels=False
    ).repair_labels is False


# ─────────────────────────────────────────────────────────────
# The command line
# ─────────────────────────────────────────────────────────────
#
# main.py was the least tested file in the repository at 34%, and the gap was
# not theoretical: the translation to Italian left ci.yml grepping `--check`
# output for English the program no longer printed, and the build went red on
# a step that had stopped testing anything. Nothing here covered the CLI, so
# nothing caught it. These do.

@pytest.fixture
def cli(tmp_path, monkeypatch):
    """The CLI pointed at a throwaway archive of genuinely fair draws.

    Fair by construction, so a test that asserted a method beat chance would
    be asserting the harness is broken.
    """
    import core.data_manager as dm
    import main as cli_module

    archive = tmp_path / "archive.csv"
    save_archive(archive, random_archive(500, seed=3))
    monkeypatch.setattr(dm, "ARCHIVE_PATH", archive)
    monkeypatch.setattr(dm, "SETTINGS_PATH", tmp_path / "settings.json")
    return cli_module


def _run(cli_module, argv, capsys):
    """Drive main() the way a shell does, and hand back (code, output)."""
    import sys as _sys

    argv_backup = _sys.argv
    _sys.argv = ["main.py", *argv]
    try:
        code = cli_module.main()
    finally:
        _sys.argv = argv_backup
    return code, capsys.readouterr().out


def test_cli_version_needs_no_archive_and_no_gui(cli, capsys):
    from core.version import __version__

    code, out = _run(cli, ["--version"], capsys)
    assert code == 0
    assert __version__ in out


def test_cli_check_runs_the_five_tests(cli, capsys):
    code, out = _run(cli, ["--check"], capsys)
    assert code == 0
    for name in ("Uniformità", "ritardi", "Indipendenza seriale",
                 "Ripetizioni", "Somma"):
        assert name in out, f"{name} missing from --check"
    # On a fair archive the summary must say so rather than flag anything.
    assert "compatibili" in out


def test_cli_check_without_an_archive_explains_and_fails(
    cli, capsys, tmp_path, monkeypatch
):
    """The contract ci.yml greps. Exit 1 and a sentence, never a traceback."""
    import core.data_manager as dm

    monkeypatch.setattr(dm, "ARCHIVE_PATH", tmp_path / "gone.csv")
    code, out = _run(cli, ["--check"], capsys)
    assert code == 1
    assert cli.NO_ARCHIVE in out


def test_cli_validate_prints_both_readings(cli, capsys):
    """The hit count and the rank statistic, because each is blind alone."""
    code, out = _run(cli, ["--validate", "120"], capsys)
    assert code == 0
    assert "centri/estrazione" in out
    assert "rango medio dei numeri usciti" in out
    assert "casuale" in out and "frequenza" in out and "ritardo" in out


def test_cli_power_reports_a_detection_floor(cli, capsys, monkeypatch):
    """Two repetitions is not a calibration, but it does drive every path.

    The real calibrate, the real power_at, the real walk_forward — only the
    repetitions are cut. At the shipped hundred this one test cost 10.8s of a
    12.9s suite, and a suite people stop running is a suite that catches
    nothing.
    """
    import functools

    import core.power as power

    monkeypatch.setattr(power, "calibrate", functools.partial(power.calibrate, runs=2))
    code, out = _run(cli, ["--power", "60"], capsys)
    assert code == 0
    for shape in power.SHAPES:
        assert shape in out
    assert "soglia al" in out


@pytest.mark.parametrize("method", ["frequenza", "ritardo", "casuale"])
def test_cli_forecast_prints_combinations(cli, capsys, method):
    code, out = _run(cli, ["--forecast", method], capsys)
    assert code == 0
    assert "escursione dei punteggi" in out
    # Six numbers on each numbered line.
    combinations = [ln for ln in out.splitlines() if ln.strip().startswith("1. ")]
    assert combinations, "no combination printed"
    assert len(combinations[0].split()) == 7          # "1." plus six numbers


def test_cli_forecast_refuses_an_unknown_method(cli, capsys):
    from core.predictor import METHODS

    code, out = _run(cli, ["--forecast", "frequency"], capsys)
    assert code == 2
    assert "sconosciuto" in out
    # And it says what would have worked.
    for method in METHODS:
        assert method in out


def test_cli_forecast_with_timesfm_missing_says_so_rather_than_raising(cli, capsys):
    """torch is not installed in the test environment, and that is the point."""
    code, out = _run(cli, ["--forecast", "timesfm"], capsys)
    assert code == 1
    assert "timesfm" in out.lower()


def test_cli_export_sqlite_writes_a_readable_database(cli, capsys, tmp_path):
    import sqlite3

    target = tmp_path / "out.db"
    code, out = _run(cli, ["--export-sqlite", str(target)], capsys)
    assert code == 0
    assert target.exists()
    with sqlite3.connect(target) as db:
        tables = {r[0] for r in db.execute(
            "select name from sqlite_master where type='table'"
        )}
    assert {"draws", "picks", "number_stats"} <= tables


def test_cli_import_is_a_dry_run_without_yes(cli, capsys, tmp_path):
    """--import and --update must not write unless told to. Twice over."""
    import core.data_manager as dm

    incoming = tmp_path / "incoming.csv"
    save_archive(incoming, random_archive(20, seed=99))
    before = dm.ARCHIVE_PATH.read_bytes()

    code, out = _run(cli, ["--import", str(incoming)], capsys)
    assert code == 0
    assert dm.ARCHIVE_PATH.read_bytes() == before, "a dry run wrote to the archive"
    assert "--yes" in out


def test_cli_import_writes_when_told_to(cli, capsys, tmp_path):
    import core.data_manager as dm

    incoming = tmp_path / "incoming.csv"
    # Dated well after the fixture archive so the merge is unambiguous.
    extra = [
        Draw(date=date(2030, 1, 1) + timedelta(days=3 * i), contest=i + 1,
             numbers=(1, 2, 3, 4, 5, 6), jolly=7, year=2030)
        for i in range(5)
    ]
    save_archive(incoming, extra)
    before = len(load_archive(dm.ARCHIVE_PATH))

    code, _ = _run(cli, ["--import", str(incoming), "--yes"], capsys)
    assert code == 0
    assert len(load_archive(dm.ARCHIVE_PATH)) == before + 5


def test_cli_import_of_a_missing_file_says_so_rather_than_raising(cli, capsys, tmp_path):
    """A named file that is not there is a typo, not a crash."""
    code, out = _run(cli, ["--import", str(tmp_path / "nope.csv")], capsys)
    assert "Import fallito" in out
    assert "file inesistente" in out
    # Exit 1, so a script driving --import notices. Not a traceback, and not
    # a silent success.
    assert code == 1


# ─────────────────────────────────────────────────────────────
# Where a frozen build puts things
# ─────────────────────────────────────────────────────────────

def test_a_frozen_build_writes_beside_the_executable(monkeypatch, tmp_path):
    """Argus lost settings to this exact mistake and its notes describe it.

    A onefile build unpacks into a temp directory and deletes it on exit, so
    ``Path(__file__).parent.parent`` inside a frozen module resolves into
    something that will not exist next run. Data has to go beside the .exe.
    """
    import core.paths as paths

    exe = tmp_path / "bundle" / "Tyche.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe))
    assert paths.writable_base_dir() == exe.parent


def test_a_frozen_build_reads_bundled_files_from_the_unpacked_payload(
    monkeypatch, tmp_path
):
    """The mirror image, and deliberately a different answer.

    Read-only resources live in _MEIPASS; writable data must not. A change
    that made these two agree would break one of them.
    """
    import core.paths as paths

    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.bundled_dir() == tmp_path


def test_running_from_source_puts_both_at_the_repository_root():
    import core.paths as paths

    repo = Path(__file__).resolve().parent.parent
    assert paths.writable_base_dir() == repo
    assert paths.bundled_dir() == repo


def test_the_bulk_source_actually_skips_the_repair_when_told_to(monkeypatch):
    """The earlier version of this checked an attribute, which proves nothing.

    A constructor flag that never reaches the code is exactly the defect this
    round was about, so the test drives fetch() over the mirror's real defect:
    the block of draws whose dates carry the wrong year, serialised back into
    the twelve-column format the source parses.
    """
    import core.sources.bulk_archive as bulk

    rows = "\n".join(
        ",".join(str(v) for v in (
            *d.numbers, d.jolly, d.superstar, d.contest,
            d.date.day, d.date.month, d.date.year,
        ))
        for d in _mislabelled_block()
    )
    monkeypatch.setattr(bulk, "http_get", lambda url, **kw: rows.encode("utf-8"))

    without = bulk.BulkArchiveSource("http://x", repair_labels=False).fetch()
    with_repair = bulk.BulkArchiveSource("http://x", repair_labels=True).fetch()

    # The repair relabels; it never drops or adds a row.
    assert len(without) == len(with_repair) == len(_mislabelled_block())

    # Unrepaired, two pairs share a contest id — which is the defect.
    assert len({d.draw_id for d in without}) < len(without)
    # Repaired, every id is distinct and the moved draws carry their numbers.
    assert len({d.draw_id for d in with_repair}) == len(with_repair)
    by_id = {d.draw_id: d for d in with_repair}
    assert by_id["1999/1"].numbers == (20, 21, 22, 23, 24, 25)
    assert by_id["1998/1"].numbers == (1, 2, 3, 4, 5, 6)


# ─────────────────────────────────────────────────────────────
# Systems and the SuperStar
# ─────────────────────────────────────────────────────────────

def test_a_system_covers_every_combination_of_six():
    from core.predictor import system_columns

    assert system_columns(6) == 1
    assert system_columns(7) == 7
    assert system_columns(9) == 84
    assert system_columns(10) == 210


def test_a_system_buys_probability_strictly_in_proportion_to_cost():
    """The one fact about systems that matters, asserted rather than asserted at.

    Playing more numbers shortens the odds and multiplies the price by exactly
    the same factor. Odds times columns is C(90,6) at every size, so the
    probability per column — per euro — never moves. A change that made a
    system look like better value would break this.
    """
    import math

    from core.predictor import SYSTEM_MAX, SYSTEM_MIN, system_columns, system_top_prize_odds

    total = math.comb(90, 6)
    for size in range(SYSTEM_MIN, SYSTEM_MAX + 1):
        product = system_top_prize_odds(size) * system_columns(size)
        # The odds are rounded to a whole number for display, so compare
        # against the exact figure with room for that rounding only.
        assert abs(product - total) / total < 1e-5, size


def test_a_system_is_refused_outside_its_range():
    from core.predictor import SYSTEM_MAX, system_columns

    with pytest.raises(ValueError, match="sistema"):
        system_columns(5)
    with pytest.raises(ValueError, match="sistema"):
        system_columns(SYSTEM_MAX + 1)


def test_the_system_profile_accounts_for_every_column():
    """Columns winning something, plus those winning nothing, is the whole system."""
    import math

    from core.predictor import system_columns, system_profile

    for size in (7, 9, 10, 12):
        for matched in range(7):
            profile = system_profile(size, matched)
            won = sum(profile.values())
            # Columns holding 0 or 1 of the drawn numbers win nothing and are
            # deliberately absent from the profile.
            nothing = sum(
                math.comb(matched, j) * math.comb(size - matched, 6 - j)
                for j in (0, 1)
            )
            assert won + nothing == system_columns(size), (size, matched)


def test_hitting_all_six_with_a_system_wins_one_six_and_many_lesser_prizes():
    """What a system actually buys, and the reason the profile is printed."""
    from core.predictor import system_profile

    profile = system_profile(10, 6)
    assert profile[6] == 1
    assert profile[5] == 24
    assert profile[4] == 90
    # A plain column wins exactly one thing and nothing else.
    assert system_profile(6, 6) == {6: 1}


def test_the_superstar_is_scored_from_its_own_drum():
    """A separate drum is a separate question, not a column of the same table."""
    from core.predictor import superstar_scores

    draws = [
        Draw(date=date(2010, 1, 1) + timedelta(days=3 * i), contest=i + 1,
             numbers=(1, 2, 3, 4, 5, 6), jolly=7, superstar=42, year=2010)
        for i in range(20)
    ]
    scores = superstar_scores(draws, window=20)
    assert scores[42] == 1.0
    # The six main numbers are drawn every time and score zero here, which is
    # the whole point: they are not what this drum produced.
    assert scores[1] == 0.0


def test_draws_from_before_the_superstar_existed_are_not_counted_as_a_number():
    """0 means "not on record" — the game began in 2006, not at number zero."""
    from core.predictor import superstar_scores

    old = [
        Draw(date=date(2000, 1, 1) + timedelta(days=3 * i), contest=i + 1,
             numbers=(1, 2, 3, 4, 5, 6), jolly=7, superstar=0, year=2000)
        for i in range(50)
    ]
    recent = [
        Draw(date=date(2010, 1, 1) + timedelta(days=3 * i), contest=i + 1,
             numbers=(1, 2, 3, 4, 5, 6), jolly=7, superstar=11, year=2010)
        for i in range(10)
    ]
    scores = superstar_scores([*old, *recent], window=60)
    # Ten recorded draws, all showing 11 — not sixty draws mostly showing zero.
    assert scores[11] == 1.0
    assert sum(scores.values()) == 1.0


def test_a_prediction_plays_the_superstar_only_when_asked():
    from core.predictor import predict

    draws = random_archive(400, seed=21)
    assert predict(draws, "frequenza").superstar is None
    star = predict(draws, "frequenza", superstar=True).superstar
    assert star is not None
    assert 1 <= star <= 90


def test_the_random_baseline_stays_random_on_the_whole_ticket():
    """The control condition has to control the SuperStar too, or it is not one."""
    from core.predictor import predict

    draws = random_archive(400, seed=22)
    stars = {
        predict(draws, "casuale", seed=s, superstar=True).superstar
        for s in range(30)
    }
    assert len(stars) > 5, "the control picked the same SuperStar every time"


def test_a_prediction_carries_the_size_it_was_asked_for():
    from core.predictor import predict

    draws = random_archive(400, seed=23)
    prediction = predict(draws, "frequenza", combinations=3, size=9)
    assert prediction.size == 9
    assert all(len(c) == 9 for c in prediction.combinations)
    with pytest.raises(ValueError, match="sistema"):
        predict(draws, "frequenza", size=20)


def test_chance_moves_with_the_number_of_picks():
    """Nine numbers is a different bet, and the backtest has to say so.

    Validating six while the ticket plays nine would compare against the wrong
    baseline: chance is picks x 6 / 90, so 0.400 becomes 0.600.
    """
    from core.validation import walk_forward

    draws = random_archive(600, seed=24)
    six = walk_forward(draws, methods=["casuale"], n_draws=200, picks=6)
    nine = walk_forward(draws, methods=["casuale"], n_draws=200, picks=9)
    assert abs(six.results[0].expected_mean - 0.4) < 1e-9
    assert abs(nine.results[0].expected_mean - 0.6) < 1e-9


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
