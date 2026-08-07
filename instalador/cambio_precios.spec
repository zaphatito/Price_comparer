# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

APP_NAME = "CambioPrecios"
SPEC_DIR = Path(SPEC).resolve().parent
PROJECT_ROOT = SPEC_DIR.parent

datas = [
    (str(PROJECT_ROOT / "views" / "main_window" / "*.ui"), "views/main_window"),
    (str(PROJECT_ROOT / "views" / "comparison_editor" / "*.ui"), "views/comparison_editor"),
    (str(PROJECT_ROOT / "assets" / "icons" / "*"), "assets/icons"),
]

relations_file = PROJECT_ROOT / "data" / "relations.xlsx"
if relations_file.exists():
    datas.append((str(relations_file), "data"))

excludes = [
    # Not needed by this app; excluding them reduces bundle size.
    "PIL",
    "PIL.Image",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "IPython",
    "jedi",
    "jupyter",
    "matplotlib",
    "notebook",
    "numba",
    "pypdfium2",
    "pypdfium2_raw",
    "pytest",
    "scipy",
    "sqlalchemy",
    "tables",
    "test",
    "tkinter",
    "unittest",
]

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
    icon=str(PROJECT_ROOT / "assets" / "icons" / "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
