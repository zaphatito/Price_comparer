from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHeaderView,
    QTableWidgetItem,
)

from ..config import DEFAULT_STORE_NAMES, PROVIDER_NAME_PROMPT
from ..utils import clean_text


class TableBehaviorMixin:
    def configure_table(self) -> None:
        self.listings_table.setColumnCount(2)
        self.listings_table.setHorizontalHeaderLabels(["Store Name", "PDF File"])
        self.listings_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.listings_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.listings_table.verticalHeader().setVisible(False)
        self.listings_table.setShowGrid(False)
        self.listings_table.setWordWrap(False)
        self.listings_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.listings_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.listings_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.listings_table.setViewportMargins(0, 0, 0, 6)
        header = self.listings_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

    def is_placeholder_visible(self) -> bool:
        if self.listings_table.rowCount() != 1:
            return False
        row_item = self.listings_table.item(0, 0)
        second_item = self.listings_table.item(0, 1)
        return (
            row_item is not None
            and second_item is None
            and row_item.data(Qt.ItemDataRole.UserRole) == "empty_placeholder"
        )

    def show_empty_list_placeholder(self) -> None:
        if self.listings_table.rowCount() > 0:
            return
        self.listings_table.clearSpans()
        self.listings_table.insertRow(0)
        placeholder = QTableWidgetItem("No PDFs added yet. Click 'Add PDF' to start.")
        placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        placeholder.setData(Qt.ItemDataRole.UserRole, "empty_placeholder")
        placeholder_font = QFont("Segoe UI", 10)
        placeholder_font.setItalic(True)
        placeholder.setFont(placeholder_font)
        self.listings_table.setItem(0, 0, placeholder)
        self.listings_table.setSpan(0, 0, 1, 2)
        self.listings_table.setRowHeight(0, 58)

    def hide_empty_list_placeholder(self) -> None:
        if not self.is_placeholder_visible():
            return
        self.listings_table.clearSpans()
        self.listings_table.removeRow(0)

    def default_name_for_index(self, index: int) -> str:
        if index < len(DEFAULT_STORE_NAMES):
            return DEFAULT_STORE_NAMES[index]
        return f"listing_{index + 1}"

    def current_pdf_paths(self) -> set[str]:
        existing = set()
        for row in range(self.listings_table.rowCount()):
            item = self.listings_table.item(row, 1)
            if item:
                existing.add(str(Path(item.text()).resolve()))
        return existing

    def current_store_names_upper(self) -> set[str]:
        names: set[str] = set()
        for row in range(self.listings_table.rowCount()):
            name_item = self.listings_table.item(row, 0)
            path_item = self.listings_table.item(row, 1)
            if name_item is None or path_item is None:
                continue
            if name_item.data(Qt.ItemDataRole.UserRole) == "empty_placeholder":
                continue
            name = clean_text(name_item.text()).upper()
            if name:
                names.add(name)
        return names

    def detect_provider_name_from_pdf(self, pdf_path: Path) -> str:
        from ..pdf_parser import detect_provider_name_from_pdf as detect_provider_name_from_pdf_file

        return detect_provider_name_from_pdf_file(pdf_path)

    def suggest_store_name_for_pdf(
        self, pdf_path: Path, existing_upper_names: set[str]
    ) -> str:
        detected_name = self.detect_provider_name_from_pdf(pdf_path)
        if detected_name == "SYSCO" and "SYSCO" in existing_upper_names:
            return PROVIDER_NAME_PROMPT
        return detected_name

    def add_row_to_table(self, list_name: str, pdf_path: Path) -> None:
        self.hide_empty_list_placeholder()
        row_idx = self.listings_table.rowCount()
        self.listings_table.insertRow(row_idx)

        name_item = QTableWidgetItem(list_name)
        path_item = QTableWidgetItem(str(pdf_path))
        path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        self.listings_table.setItem(row_idx, 0, name_item)
        self.listings_table.setItem(row_idx, 1, path_item)

    def add_paths(self, paths: list[Path]) -> None:
        if not paths:
            return
        existing = self.current_pdf_paths()
        existing_store_names = self.current_store_names_upper()
        added = 0
        skipped = 0

        for path in paths:
            resolved = path.resolve()
            if resolved.suffix.lower() != ".pdf":
                skipped += 1
                continue
            if str(resolved) in existing:
                skipped += 1
                continue

            if self.is_placeholder_visible():
                self.hide_empty_list_placeholder()
            suggested_name = self.suggest_store_name_for_pdf(resolved, existing_store_names)
            self.add_row_to_table(suggested_name, resolved)
            existing.add(str(resolved))
            existing_store_names.add(clean_text(suggested_name).upper())
            added += 1

        if self.listings_table.rowCount() == 0:
            self.show_empty_list_placeholder()
        self.log_output.append(f"PDFs added: {added} | skipped: {skipped}")

    def add_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select PDF Files",
            str(self.downloads_dir),
            "PDF Files (*.pdf)",
        )
        self.add_paths([Path(file_path) for file_path in files])

    def remove_selected_rows(self) -> None:
        selected_rows = sorted(
            {item.row() for item in self.listings_table.selectedItems()},
            reverse=True,
        )
        if not selected_rows:
            return

        for row_idx in selected_rows:
            self.listings_table.removeRow(row_idx)
        if self.listings_table.rowCount() == 0:
            self.show_empty_list_placeholder()
        self.log_output.append(f"Rows removed: {len(selected_rows)}")

    def clear_rows(self) -> None:
        if self.listings_table.rowCount() == 0 or self.is_placeholder_visible():
            return
        self.listings_table.setRowCount(0)
        self.show_empty_list_placeholder()
        self.log_output.append("List cleared.")

    def on_item_changed(self, item: QTableWidgetItem) -> None:
        if self.loading_table:
            return
        if item.column() != 0:
            return

        row = item.row()
        new_name = clean_text(item.text())
        if new_name:
            return

        fallback_name = self.default_name_for_index(row)
        self.loading_table = True
        item.setText(fallback_name)
        self.loading_table = False
