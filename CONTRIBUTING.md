# Contributing

Tyche is a single-author project and a small one. Nothing here is meant to
discourage a patch — this file exists so that a patch does not have to guess
at the conventions.

## The licence

Tyche is **AGPL-3.0-or-later**. A contribution is offered under the same
licence, which is the default the AGPL itself sets and needs no paperwork:
there is no CLA and no copyright assignment. Nobody signs anything.

That is a consequence of there being no commercial licence. A CLA exists so a
project can relicense contributed code under terms the contributor did not
choose — which is what dual licensing needs and what Tyche does not do.

Every source file carries the SPDX header. New files carry it too.

## Before opening a pull request

```
python -m ruff check .
TYCHE_REQUIRE_GUI=1 xvfb-run -a python -m pytest tests/ -q
```

Both must pass. The second command matters more than it looks: without
`TYCHE_REQUIRE_GUI=1` the interface tests skip themselves when there is no
display and the run reports green having tested no interface at all.

`CLAUDE.md` documents the conventions this repository actually follows,
including several that exist because getting them wrong cost somebody a day.
It is worth reading before a change to the archive parsers, the validation
harness or the release workflow.

## What a change should carry

**A measurement rather than an argument, where one is available.** Several
decisions in this program — one combination rather than five, the mid-rank
tie-break, the size of edge the backtest can detect — were settled by running
the thing and reading the number, and the numbers are recorded next to the
code. A change that overturns one of them is welcome and should overturn it
the same way.

**A test that fails without it.** Checked by removing the change and watching
the test go red, not by assuming. This repository has more than once had a
test that passed either way.

**Nothing that makes a lottery look winnable.** The random baseline sits in
the method menu at the same size as the 330M-parameter model, the validation
report prints every method, and the system arithmetic states that probability
per euro never moves. Those are load-bearing and each has a test. A change
that quietly removed one would be refused even if it were otherwise perfect.

## Reporting something

Open an issue with what you ran, what you expected and what happened. If it
concerns the archive, the output of `python main.py --check` and the draw
count from the footer are usually enough to place it.
