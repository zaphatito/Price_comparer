from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QSize, QThread
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QProgressBar,
    QStyle,
    QTableWidget,
    QTextEdit,
    QWidget,
)

if __package__:
    from .config import APP_DIR, DEFAULT_OUTPUT_FILE, MAIN_WINDOW_VIEWS_DIR
    from .ui import ConversionBehaviorMixin, TableBehaviorMixin
    from .ui_loader import load_designer_widget
    from .utils import get_downloads_dir
else:
    PROJECT_DIR = Path(__file__).resolve().parents[1]
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))
    from app.config import APP_DIR, DEFAULT_OUTPUT_FILE, MAIN_WINDOW_VIEWS_DIR
    from app.ui import ConversionBehaviorMixin, TableBehaviorMixin
    from app.ui_loader import load_designer_widget
    from app.utils import get_downloads_dir

if TYPE_CHECKING:
    if __package__:
        from .conversion_worker import ConversionWorker
    else:
        from app.conversion_worker import ConversionWorker


class MainWindow(
    QMainWindow,
    TableBehaviorMixin,
    ConversionBehaviorMixin,
):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Price Comparator")

        ui_path = self.resolve_ui_path()
        self.setCentralWidget(load_designer_widget(ui_path))
        self.apply_initial_window_size()

        self.thread: QThread | None = None
        self.worker: ConversionWorker | None = None
        self.pending_result: dict | None = None
        self.loading_table = False
        self.downloads_dir = get_downloads_dir()
        self.current_theme_mode: str | None = None
        self.is_applying_theme = False
        self._centered_once = False

        self.header_card = self.get_widget(QFrame, "headerCard")
        self.actions_card = self.get_widget(QFrame, "actionsCard")
        self.table_card = self.get_widget(QFrame, "tableCard")
        self.output_card = self.get_widget(QFrame, "outputCard")
        self.logs_card = self.get_widget(QFrame, "logsCard")
        self.title_label = self.get_widget(QLabel, "titleLabel")
        self.subtitle_label = self.get_widget(QLabel, "subtitleLabel")
        self.listings_label = self.get_widget(QLabel, "listingsLabel")
        self.log_label = self.get_widget(QLabel, "logLabel")

        self.add_pdf_btn = self.get_widget(QPushButton, "addPdfBtn")
        self.remove_selected_btn = self.get_widget(QPushButton, "removeSelectedBtn")
        self.clear_btn = self.get_widget(QPushButton, "clearBtn")
        self.download_relations_btn = self.get_widget(QPushButton, "downloadRelationsBtn")
        self.upload_relations_btn = self.get_widget(QPushButton, "uploadRelationsBtn")
        self.download_icon_light_path = APP_DIR / "assets" / "icons" / "download_relations_light.svg"
        self.download_icon_dark_path = APP_DIR / "assets" / "icons" / "download_relations_dark.svg"
        self.listings_table_container = self.get_widget(QFrame, "listingsTableContainer")
        self.listings_table = self.get_widget(QTableWidget, "listingsTable")
        self.output_dir_value = self.get_widget(QLabel, "outputDirValueLabel")
        self.output_file_input = self.get_widget(QLineEdit, "outputFileInput")
        self.progress_label = self.get_widget(QLabel, "progressLabel")
        self.progress_bar = self.get_widget(QProgressBar, "progressBar")
        self.convert_btn = self.get_widget(QPushButton, "convertBtn")
        self.log_output = self.get_widget(QTextEdit, "logOutput")

        self.ui_stylesheet = self.load_stylesheet_from_ui(
            MAIN_WINDOW_VIEWS_DIR / "main_window.ui"
        )

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.apply_system_theme(force=True)

        self.configure_table()
        self.show_empty_list_placeholder()
        self.output_dir_value.setText(str(self.downloads_dir))
        self.output_file_input.setText(DEFAULT_OUTPUT_FILE)
        self.progress_label.setText("Progress: 0/0")
        self.progress_bar.setValue(0)
        self.configure_relations_buttons()

        self.add_pdf_btn.clicked.connect(self.add_pdfs)
        self.remove_selected_btn.clicked.connect(self.remove_selected_rows)
        self.clear_btn.clicked.connect(self.clear_rows)
        self.download_relations_btn.clicked.connect(self.download_relations_sheet)
        self.upload_relations_btn.clicked.connect(self.load_relations_sheet)
        self.convert_btn.clicked.connect(self.start_conversion)
        self.listings_table.itemChanged.connect(self.on_item_changed)

        self.log_output.append(f"Excel output folder: {self.downloads_dir}")

    def apply_initial_window_size(self) -> None:
        central_widget = self.centralWidget()
        if central_widget is None:
            return

        base_size = central_widget.size()
        if not base_size.isValid() or base_size.isEmpty():
            base_size = central_widget.sizeHint()

        minimum_size = central_widget.minimumSize()
        if minimum_size.isValid() and not minimum_size.isEmpty():
            self.setMinimumSize(minimum_size)
            base_size = base_size.expandedTo(minimum_size)

        # Keep startup width pinned to the UI minimum width.
        if minimum_size.isValid() and minimum_size.width() > 0:
            base_size.setWidth(minimum_size.width())

        app = QApplication.instance()
        screen = self.screen()
        if screen is None and app is not None:
            screen = app.primaryScreen()

        if screen is not None:
            available_size = screen.availableGeometry().size()
            max_height = max(minimum_size.height(), int(available_size.height() * 0.90))
            base_size.setHeight(min(base_size.height(), max_height))

        self.resize(base_size)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._centered_once:
            return
        self._centered_once = True
        self.center_on_screen()

    def center_on_screen(self) -> None:
        screen = self.screen()
        if screen is None:
            app = QApplication.instance()
            if app is not None:
                screen = app.primaryScreen()
        if screen is None:
            return

        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    def configure_relations_buttons(self) -> None:
        style = self.style()
        self.upload_relations_btn.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.download_relations_btn.setIconSize(QSize(18, 18))
        self.upload_relations_btn.setIconSize(QSize(18, 18))
        self.download_relations_btn.setToolTip("Download relations sheet")
        self.upload_relations_btn.setToolTip("Load relations sheet")
        self.apply_download_icon_for_mode(self.current_theme_mode or self.detect_system_theme_mode())

    def apply_download_icon_for_mode(self, mode: str) -> None:
        icon_path = self.download_icon_dark_path if mode == "dark" else self.download_icon_light_path
        if icon_path.exists():
            self.download_relations_btn.setIcon(QIcon(str(icon_path)))
            return

        style = self.style()
        self.download_relations_btn.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        )

    def eventFilter(self, watched, event) -> bool:
        app = QApplication.instance()
        if (
            watched is app
            and event.type()
            in (QEvent.Type.ApplicationPaletteChange, QEvent.Type.PaletteChange)
            and not self.is_applying_theme
        ):
            self.apply_system_theme()
        return super().eventFilter(watched, event)

    def detect_system_theme_mode(self) -> str:
        app = QApplication.instance()
        if app is None:
            return "light"

        palette = app.palette()
        window_lightness = palette.color(QPalette.ColorRole.Window).lightness()
        base_lightness = palette.color(QPalette.ColorRole.Base).lightness()
        avg_lightness = (window_lightness + base_lightness) / 2
        return "dark" if avg_lightness < 128 else "light"

    def apply_system_theme(self, force: bool = False) -> None:
        if self.is_applying_theme:
            return

        mode = self.detect_system_theme_mode()
        if not force and mode == self.current_theme_mode:
            return

        self.is_applying_theme = True
        try:
            root_widget = self.centralWidget()
            root_widget.setProperty("themeMode", mode)
            root_widget.setStyleSheet(self.ui_stylesheet)
            root_widget.style().unpolish(root_widget)
            root_widget.style().polish(root_widget)
            root_widget.update()
            self.current_theme_mode = mode
            self.apply_download_icon_for_mode(mode)
        finally:
            self.is_applying_theme = False

    def load_stylesheet_from_ui(self, ui_path: Path) -> str:
        try:
            tree = ET.parse(ui_path)
        except (ET.ParseError, OSError):
            return ""

        for prop in tree.getroot().iter("property"):
            if prop.get("name") != "styleSheet":
                continue
            style_node = prop.find("string")
            if style_node is not None and style_node.text is not None:
                return style_node.text
            return ""
        return ""

    def resolve_ui_path(self) -> Path:
        return MAIN_WINDOW_VIEWS_DIR / "main_window.ui"

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(2000)

        super().closeEvent(event)

    def get_widget(self, widget_type: type[QWidget], object_name: str):
        widget = self.centralWidget().findChild(widget_type, object_name)
        if widget is None:
            raise RuntimeError(f"Widget '{object_name}' was not found in the .ui file")
        return widget


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
