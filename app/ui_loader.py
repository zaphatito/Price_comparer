from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QIODevice, QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget


def load_designer_widget(ui_path: Path) -> QWidget:
    loader = QUiLoader()
    ui_file = QFile(str(ui_path))
    if not ui_file.open(QIODevice.ReadOnly):
        raise FileNotFoundError(f"Could not open UI file: {ui_path}")
    try:
        widget = loader.load(ui_file)
    finally:
        ui_file.close()

    if widget is None:
        raise RuntimeError(f"Could not load UI: {ui_path}")

    return widget
