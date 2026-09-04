# Tyche.spec — PyInstaller build specification
#
# `python build.py` is the way to run this. It produces a Windows folder build
# under dist/Tyche/, which the release workflow zips.
#
# **A folder, not a single file, and that is the one real divergence from
# Argus's spec.** Argus freezes to --onefile, which is tidier: one executable,
# nothing to unpack. A onefile build works by packing everything into the
# executable and extracting it to a temporary folder on *every* launch. Argus
# gets away with it. Tyche bundles PyTorch: the built folder is around 400 MB
# and zips to 160 MB, and extracting that on every start would mean waiting to
# see a window every single time. A folder build starts immediately and the
# archive is no bigger for it.
#
# User data — config/settings.json, data/ — is written next to the executable,
# not inside the bundle. core/paths.py::writable_base_dir is the single place
# that decides that, and it reads sys.executable when frozen, which for a
# folder build is dist/Tyche/Tyche.exe. Copy the folder anywhere and the
# archive travels with it.
#
# Torch decides how big this gets. Build from a virtualenv with the CPU-only
# wheel installed (pip install torch --index-url
# https://download.pytorch.org/whl/cpu) — whatever torch is present when this
# runs is the one that gets bundled, and the default CUDA build from PyPI adds
# several gigabytes of NVIDIA runtime that only pays off on a matching GPU.
#
# What is NOT in here: the TimesFM checkpoint. It is 1.3 GB, it is downloaded
# from Hugging Face on first use, and its licence is non-commercial while the
# package code around it is Apache-2.0. Bundling weights would make the
# archive a redistribution of them, which is a different question from running
# them locally.

import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

# CustomTkinter ships its themes and fonts as package data (JSON and TTF under
# customtkinter/assets/). Without this the import succeeds, the first widget
# raises, and the failure looks nothing like a missing data file.
datas = collect_data_files("customtkinter")
binaries = []
hiddenimports = []

# timesfm3 is imported lazily by core/forecaster.py, so PyInstaller's static
# analysis never sees it: without collect_all the frozen build would report
# "timesfm is not installed" no matter what was in the build environment.
# Optional on purpose — a build machine without torch produces a smaller
# bundle that does everything except the TimesFM forecast, and says so through
# --self-check rather than failing here.
for package in ("timesfm3", "timesfm"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except Exception as exc:                                    # noqa: BLE001
        print(f"[Tyche.spec] {package} not collected: {exc}")
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # readline is excluded for a licensing reason rather than for size:
    # PyInstaller collects the standard library's optional readline
    # extension, which links libreadline — GPL-3.0-or-later with no linking
    # exception. Tyche is a windowed program that never reads a line from an
    # interactive prompt. rlcompleter goes with it; it imports readline and
    # exists for nothing else. Argus excludes the same pair.
    #
    # The test frameworks are excluded because PyInstaller otherwise follows
    # an import in a dependency and drags pytest into a shipped binary.
    excludes=["readline", "rlcompleter", "pytest", "_pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Tyche",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # console=False on Windows: a windowed program should not have a terminal
    # behind it. It also means the process has no stdout, which is why
    # --self-check writes its report to a file.
    console=sys.platform != "win32",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Tyche",
)
