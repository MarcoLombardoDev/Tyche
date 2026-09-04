# Changelog

Notable changes per release. The section for a version is what the release
page shows: `tools/release_notes.py` reads it out of this file and composes it
with the standing preamble in `.github/release-body.md`, so the notes and this
file cannot drift apart.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0] — 2026-09-04

First release.

### The archive

- Draw history from **3 December 1997 to the present**, 4,260 draws, fetched
  from estrazioni.it in one request. `--update` refreshes it; `--import`
  reads a file downloaded by hand; a mirrored bulk CSV bootstraps an empty
  archive without configuration; a per-year HTML scrape is the last resort.
- Every write is previewed first. Rows that would contradict a stored draw,
  and integrity errors a merge would introduce, are reported before anything
  is written, and the sources whose URLs are inferred rather than documented
  always ask.
- `integrity_report` checks the sequence, not just the rows: duplicated
  dates, duplicated contest numbers, gaps inside a complete year. It found
  nine draws of 1999 labelled 1998 in the bulk mirror, and
  `repair_year_offset` puts them back — verified against an independent
  source, including the two that share a date with their duplicate.
- How far behind the archive is, in draws, is on screen rather than in the
  documentation, measured against the archive's own cadence.

### The measurement

- Five tests of the hypothesis that the draws are independent and uniform:
  per-number uniformity, the gap (*ritardo*) distribution, serial
  independence, repeats between consecutive draws, and the sum of the six.
- Walk-forward backtesting with no look-ahead, scored against the closed-form
  hypergeometric null — chance is 0.4 hits per draw, exactly. TimesFM, hot
  numbers, *ritardo* and a random number generator are all scored over the
  same draws and all reported.
- Exact prize-category odds, and a SQLite export for querying the archive
  with SQL.

### The forecast

- TimesFM 3.0 (`google/timesfm-3.0-pytorch`, 330M parameters) over ninety
  per-number series. Verified end to end in CI, on the real checkpoint.
- Nothing beats chance. That is the finding, not a caveat: over the last
  1,000 draws the foundation model, the two folk heuristics and the random
  baseline all score 0.4.
