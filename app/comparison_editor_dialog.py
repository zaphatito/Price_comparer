from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config import COMPARISON_EDITOR_VIEWS_DIR
from .ui_loader import load_designer_widget
from .utils import clean_text


class ComparisonEditorDialog(QDialog):
    def __init__(
        self,
        store_columns: list[str],
        store_catalog: dict[str, list[dict[str, object]]],
        relation_rows: list[dict[str, object]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Edit Comparisons")
        self.resize(1260, 780)

        theme_mode = self.detect_theme_mode(parent)
        root_widget = load_designer_widget(self.resolve_ui_path())
        root_widget.setProperty("themeMode", theme_mode)
        root_widget.style().unpolish(root_widget)
        root_widget.style().polish(root_widget)
        root_widget.update()
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(root_widget)

        self.store_columns = store_columns
        self.store_catalog = store_catalog
        self.saved_rows: list[dict[str, object]] | None = None

        self.table = self.get_widget(root_widget, QTableWidget, "comparisonTable")
        self.status_label = self.get_widget(root_widget, QLabel, "statusLabel")
        self.add_row_btn = self.get_widget(root_widget, QPushButton, "addRowBtn")
        self.remove_row_btn = self.get_widget(root_widget, QPushButton, "removeRowBtn")
        self.cancel_btn = self.get_widget(root_widget, QPushButton, "cancelBtn")
        self.save_btn = self.get_widget(root_widget, QPushButton, "saveBtn")

        self.catalog_by_store_key: dict[str, dict[str, dict[str, object]]] = {}
        self.catalog_options_by_store: dict[str, list[dict[str, object]]] = {}
        for store_name in self.store_columns:
            options = sorted(
                store_catalog.get(store_name, []),
                key=lambda item: str(item["product_name"]).lower(),
            )
            self.catalog_options_by_store[store_name] = options
            self.catalog_by_store_key[store_name] = {
                str(item["product_key"]): item for item in options
            }

        self.configure_table()

        for row in relation_rows:
            stores = row.get("stores", {})
            selected_keys = {
                store_name: (
                    str(stores[store_name]["product_key"])
                    if stores.get(store_name) is not None
                    else ""
                )
                for store_name in self.store_columns
            }
            self.append_row(
                product_name=clean_text(row.get("product_name", "")),
                selected_keys=selected_keys,
            )

        if self.table.rowCount() == 0:
            self.append_row(product_name="", selected_keys={})

        self.add_row_btn.clicked.connect(self.on_add_row)
        self.remove_row_btn.clicked.connect(self.on_remove_rows)
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.save_and_accept)

        self.refresh_status()

    def resolve_ui_path(self) -> Path:
        return COMPARISON_EDITOR_VIEWS_DIR / "comparison_editor.ui"

    def detect_theme_mode(self, parent: QWidget | None) -> str:
        parent_mode = clean_text(getattr(parent, "current_theme_mode", ""))
        if parent_mode in {"light", "dark"}:
            return parent_mode

        app = QApplication.instance()
        if app is None:
            return "light"

        palette = app.palette()
        window_lightness = palette.color(QPalette.ColorRole.Window).lightness()
        base_lightness = palette.color(QPalette.ColorRole.Base).lightness()
        avg_lightness = (window_lightness + base_lightness) / 2
        return "dark" if avg_lightness < 128 else "light"

    def get_widget(self, root: QWidget, widget_type: type[QWidget], object_name: str):
        widget = root.findChild(widget_type, object_name)
        if widget is None:
            raise RuntimeError(f"Widget '{object_name}' was not found in comparison editor UI.")
        return widget

    def configure_table(self) -> None:
        headers = ["Product Group"]
        for store_name in self.store_columns:
            headers.append(f"{store_name} Item")
            headers.append(f"{store_name} Price")

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for idx in range(len(self.store_columns)):
            item_col = 1 + idx * 2
            price_col = item_col + 1
            header.setSectionResizeMode(item_col, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(price_col, QHeaderView.ResizeMode.ResizeToContents)

    def create_store_combo(self, store_name: str, selected_key: str) -> QComboBox:
        combo = QComboBox(self.table)
        combo.addItem("", "")
        for option in self.catalog_options_by_store.get(store_name, []):
            combo.addItem(str(option["product_name"]), str(option["product_key"]))

        if selected_key:
            selected_index = combo.findData(selected_key)
            if selected_index >= 0:
                combo.setCurrentIndex(selected_index)

        combo.currentIndexChanged.connect(self.on_combo_changed)
        return combo

    def append_row(self, product_name: str, selected_keys: dict[str, str]) -> None:
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)

        group_item = QTableWidgetItem(product_name)
        group_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.table.setItem(row_idx, 0, group_item)

        for idx, store_name in enumerate(self.store_columns):
            item_col = 1 + idx * 2
            price_col = item_col + 1

            combo = self.create_store_combo(store_name, selected_keys.get(store_name, ""))
            self.table.setCellWidget(row_idx, item_col, combo)

            price_item = QTableWidgetItem("")
            price_item.setFlags(price_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            self.table.setItem(row_idx, price_col, price_item)

        self.update_row_prices(row_idx)
        self.table.setRowHeight(row_idx, 32)

    def on_combo_changed(self) -> None:
        for row_idx in range(self.table.rowCount()):
            self.update_row_prices(row_idx)
        self.refresh_status()

    def update_row_prices(self, row_idx: int) -> None:
        for idx, store_name in enumerate(self.store_columns):
            item_col = 1 + idx * 2
            price_col = item_col + 1
            combo = self.table.cellWidget(row_idx, item_col)
            price_item = self.table.item(row_idx, price_col)
            if not isinstance(combo, QComboBox) or price_item is None:
                continue

            product_key = clean_text(combo.currentData())
            if not product_key:
                price_item.setText("")
                continue

            selected = self.catalog_by_store_key.get(store_name, {}).get(product_key)
            if selected is None:
                price_item.setText("")
                continue

            price_value = float(selected["price"])
            price_item.setText(f"${price_value:,.2f}")

    def on_add_row(self) -> None:
        self.append_row(product_name="", selected_keys={})
        self.refresh_status()

    def on_remove_rows(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            return

        for row_idx in selected_rows:
            self.table.removeRow(row_idx)

        if self.table.rowCount() == 0:
            self.append_row(product_name="", selected_keys={})

        self.refresh_status()

    def collect_manual_rows(self) -> list[dict[str, object]]:
        manual_rows: list[dict[str, object]] = []
        for row_idx in range(self.table.rowCount()):
            group_item = self.table.item(row_idx, 0)
            group_name = clean_text(group_item.text()) if group_item is not None else ""

            stores: dict[str, str] = {}
            fallback_name = ""
            for idx, store_name in enumerate(self.store_columns):
                item_col = 1 + idx * 2
                combo = self.table.cellWidget(row_idx, item_col)
                if not isinstance(combo, QComboBox):
                    continue

                product_key = clean_text(combo.currentData())
                if not product_key:
                    continue

                stores[store_name] = product_key
                selected = self.catalog_by_store_key.get(store_name, {}).get(product_key)
                if fallback_name == "" and selected is not None:
                    fallback_name = clean_text(selected["product_name"])

            if not stores:
                continue

            if not group_name:
                group_name = fallback_name or f"group_{len(manual_rows) + 1}"

            manual_rows.append(
                {
                    "product_name": group_name,
                    "stores": stores,
                }
            )

        return manual_rows

    def validate_unique_products(self, manual_rows: list[dict[str, object]]) -> str | None:
        by_store: dict[str, dict[str, int]] = defaultdict(dict)

        for row_idx, row in enumerate(manual_rows, start=1):
            stores = row.get("stores", {})
            if not isinstance(stores, dict):
                continue
            for store_name, product_key in stores.items():
                key = clean_text(product_key)
                if not key:
                    continue
                if key in by_store[store_name]:
                    first_row = by_store[store_name][key]
                    return (
                        f"Duplicate product detected in '{store_name}' "
                        f"(rows {first_row} and {row_idx})."
                    )
                by_store[store_name][key] = row_idx

        return None

    def save_and_accept(self) -> None:
        manual_rows = self.collect_manual_rows()
        duplicate_error = self.validate_unique_products(manual_rows)
        if duplicate_error:
            QMessageBox.warning(self, "Invalid comparison rows", duplicate_error)
            return

        self.saved_rows = manual_rows
        self.accept()

    def refresh_status(self) -> None:
        non_empty_rows = len(self.collect_manual_rows())
        self.status_label.setText(
            f"Rows: {self.table.rowCount()} | Non-empty comparison rows: {non_empty_rows}"
        )
