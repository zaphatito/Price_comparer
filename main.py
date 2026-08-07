from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import APP_DIR
from app.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    icon_path = APP_DIR / "assets" / "icons" / "app_icon.ico"
    if not icon_path.exists():
        icon_path = APP_DIR / "assets" / "icons" / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
