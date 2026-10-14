# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for JobSprint. Build with:
    venv\\Scripts\\pyinstaller.exe packaging\\jobsprint.spec --noconfirm

Onedir (not onefile) — an app mixing uvicorn + pywebview + a Playwright
driver subprocess is more reliable un-archived; onefile's per-launch temp
extraction adds startup latency and another failure mode for no real benefit
on a locally-installed desktop app.

Bundles the `playwright` package's data files (its `driver/` folder — the
Node.js runtime + CLI Playwright itself ships and calls to manage browsers)
and jobsprint's own static assets. Exact hidden-import list came from iterating
against real PyInstaller "ModuleNotFoundError at runtime" failures, not
guessed up front — uvicorn and Playwright both do import-time magic that
static analysis can't always see through.
"""

import os

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "jobsprint", "dashboard", "static"), "jobsprint/dashboard/static"),
    (os.path.join(ROOT, "jobsprint", "knowledge", "schema.sql"), "jobsprint/knowledge"),
]
datas += collect_data_files("playwright")

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [os.path.join(ROOT, "packaging", "entry_point.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JobSprint",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="JobSprint",
)
