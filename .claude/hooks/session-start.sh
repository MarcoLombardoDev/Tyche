#!/bin/bash
# Tyche — SessionStart hook for Claude Code on the web.
#
# Puts the session in a state where the *whole* test suite runs, GUI included:
#
#   TYCHE_REQUIRE_GUI=1 xvfb-run -a python -m pytest tests/ -q
#
# That is harder than it looks, and CLAUDE.md explains why: tkinter is an OS
# package and it has to belong to the interpreter that actually runs the
# tests. On this image `apt install python3-tk` installs the module for the
# distribution's Python while `python3` resolves to a different build from
# /usr/local/bin, so the obvious two commands leave the GUI suite skipping
# itself and the run reporting green. The fix is to find the interpreter that
# can import tkinter *after* the apt install and build the virtualenv from
# that one, with --system-site-packages so it can see it.
#
# Deliberately not installed: torch and timesfm, which are gigabytes and which
# no test needs — core/forecaster.py reports a missing model rather than
# raising, and there is a test asserting exactly that. Install them by hand in
# a session that intends to run a real forecast:
#
#   pip install torch --index-url https://download.pytorch.org/whl/cpu
#   pip install -r requirements.txt

set -euo pipefail

# Local runs have their own environment and their own opinions about it.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

echo "[tyche-setup] installing Tk and Xvfb"
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq python3-tk xvfb >/dev/null

# The interpreter for the virtualenv: the first one that can import tkinter.
# Ordered newest first, with `python3` last so an explicitly versioned build
# that works beats the default one that may not.
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import tkinter" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "[tyche-setup] WARNING: no interpreter can import tkinter." >&2
  echo "[tyche-setup] The core suite will run; the GUI suite will refuse to" >&2
  echo "[tyche-setup] with TYCHE_REQUIRE_GUI=1, which is the intended failure." >&2
  PYTHON="python3"
fi
echo "[tyche-setup] building .venv from $PYTHON ($("$PYTHON" -V 2>&1))"

# --system-site-packages is what lets the venv see the apt-installed tkinter.
# Re-running `venv` over an existing directory is safe and cheap, which is
# what keeps this hook idempotent across resumes.
"$PYTHON" -m venv --system-site-packages .venv

# The runtime dependencies the tests actually import, plus the tooling.
# `pip install` rather than a locked sync, so the cached container layer is
# reused on the next session instead of being rebuilt.
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet numpy requests customtkinter pytest ruff pillow

# Prepend the venv so `python`, `pytest` and `ruff` are the right ones for the
# rest of the session.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export PATH=\"$PWD/.venv/bin:\$PATH\""
    echo "export PYTHONPATH=\"$PWD\""
  } >> "$CLAUDE_ENV_FILE"
fi

if ./.venv/bin/python -c "import tkinter" >/dev/null 2>&1; then
  echo "[tyche-setup] ready — TYCHE_REQUIRE_GUI=1 xvfb-run -a python -m pytest tests/ -q"
else
  echo "[tyche-setup] ready, but without tkinter: the GUI suite cannot run here."
fi
