from __future__ import annotations

import hashlib
import json
from shutil import copy2
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ..config import (
    DEFAULT_OUTPUT_FILE,
    DEFAULT_STORE_NAMES,
    LEGACY_PRIORITY_RELATIONS_FILE,
    MANUAL_COMPARISONS_FILE,
    PRIORITY_RELATIONS_FILE,
)
from ..models import ListingEntry
from ..relations_sheet import relations_df_to_manual_rows, relations_df_to_standard
from ..utils import clean_text, ensure_unique_names


class ConversionBehaviorMixin:
    def ensure_priority_relations_location(self) -> None:
        if PRIORITY_RELATIONS_FILE.exists():
            return
        if not LEGACY_PRIORITY_RELATIONS_FILE.exists():
            return

        try:
            PRIORITY_RELATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            LEGACY_PRIORITY_RELATIONS_FILE.replace(PRIORITY_RELATIONS_FILE)
        except OSError as exc:
            self.log_output.append(
                f"[WARN] Could not move legacy relations file to '{PRIORITY_RELATIONS_FILE}': {exc}"
            )
            return

        self.log_output.append(
            f"[INFO] Legacy relations moved to: {PRIORITY_RELATIONS_FILE}"
        )

    def collect_entries(self) -> list[ListingEntry]:
        entries: list[ListingEntry] = []
        for row in range(self.listings_table.rowCount()):
            name_item = self.listings_table.item(row, 0)
            path_item = self.listings_table.item(row, 1)
            if not name_item or not path_item:
                continue

            list_name = clean_text(name_item.text()) or self.default_name_for_index(row)
            pdf_path = Path(path_item.text())
            entries.append(ListingEntry(list_name=list_name, pdf_path=pdf_path))

        return entries

    def set_controls_enabled(self, enabled: bool) -> None:
        self.add_pdf_btn.setEnabled(enabled)
        self.remove_selected_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
        if hasattr(self, "download_relations_btn"):
            self.download_relations_btn.setEnabled(enabled)
        if hasattr(self, "upload_relations_btn"):
            self.upload_relations_btn.setEnabled(enabled)
        self.listings_table.setEnabled(enabled)
        self.output_file_input.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)

    def validate_entries(self, entries: list[ListingEntry]) -> bool:
        if not entries:
            QMessageBox.warning(self, "No PDFs", "Add at least one PDF to the list.")
            return False

        missing = [str(entry.pdf_path) for entry in entries if not entry.pdf_path.exists()]
        if missing:
            QMessageBox.warning(
                self,
                "Missing files",
                "These PDF files do not exist:\n" + "\n".join(missing[:8]),
            )
            return False

        return True

    def build_named_entries(self, entries: list[ListingEntry]) -> list[tuple[ListingEntry, str]]:
        unique_names = ensure_unique_names([entry.list_name for entry in entries])
        return list(zip(entries, unique_names))

    def build_comparison_signature(
        self,
        named_entries: list[tuple[ListingEntry, str]],
    ) -> str:
        signature_parts = []
        for entry, store_name in named_entries:
            resolved_path = str(entry.pdf_path.resolve()).lower()
            signature_parts.append(f"{clean_text(store_name).upper()}|{resolved_path}")
        signature_parts.sort()
        payload = "\n".join(signature_parts)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def ensure_manual_comparisons_loaded(self) -> None:
        if hasattr(self, "manual_comparisons"):
            return
        self.manual_comparisons = self.load_manual_comparisons()

    def load_manual_comparisons(self) -> dict[str, list[dict[str, object]]]:
        if not MANUAL_COMPARISONS_FILE.exists():
            return {}

        try:
            payload = json.loads(MANUAL_COMPARISONS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        raw_comparisons = payload.get("comparisons", {})
        if not isinstance(raw_comparisons, dict):
            return {}

        comparisons: dict[str, list[dict[str, object]]] = {}
        for signature, rows in raw_comparisons.items():
            if not isinstance(signature, str) or not isinstance(rows, list):
                continue
            valid_rows: list[dict[str, object]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                stores = row.get("stores", {})
                if not isinstance(stores, dict):
                    continue
                normalized_stores: dict[str, str] = {}
                for store_name, product_key in stores.items():
                    store_text = clean_text(store_name)
                    key_text = clean_text(product_key)
                    if store_text and key_text:
                        normalized_stores[store_text] = key_text
                if not normalized_stores:
                    continue
                valid_rows.append(
                    {
                        "product_name": clean_text(row.get("product_name", "")),
                        "stores": normalized_stores,
                    }
                )
            comparisons[signature] = valid_rows

        return comparisons

    def save_manual_comparisons(self) -> None:
        self.ensure_manual_comparisons_loaded()
        payload = {
            "version": 1,
            "comparisons": self.manual_comparisons,
        }
        MANUAL_COMPARISONS_FILE.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    def build_output_path(self) -> Path:
        output_file = clean_text(self.output_file_input.text()) or DEFAULT_OUTPUT_FILE
        if not output_file.lower().endswith(".xlsx"):
            output_file += ".xlsx"
        return self.downloads_dir / output_file

    def _relations_df_to_manual_rows(
        self,
        relations_df: pd.DataFrame,
        store_columns: list[str],
    ) -> list[dict[str, object]]:
        return relations_df_to_manual_rows(relations_df, store_columns)

    def load_manual_rows_from_excel(
        self,
        output_path: Path,
        store_columns: list[str],
    ) -> list[dict[str, object]] | None:
        if not output_path.exists():
            return None

        try:
            with pd.ExcelFile(output_path) as workbook:
                preferred_sheet = None
                if "Relations" in workbook.sheet_names:
                    preferred_sheet = "Relations"
                elif "Cuadro_Relaciones" in workbook.sheet_names:
                    preferred_sheet = "Cuadro_Relaciones"

                if preferred_sheet is None:
                    if not workbook.sheet_names:
                        return None
                    preferred_sheet = workbook.sheet_names[0]

                relations_df = workbook.parse(preferred_sheet)
        except Exception:
            return None

        return self._relations_df_to_manual_rows(relations_df, store_columns)

    def _deduplicate_manual_rows(
        self,
        rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        unique_rows: list[dict[str, object]] = []
        seen_signatures: set[tuple[tuple[str, str], ...]] = set()

        for row in rows:
            stores = row.get("stores")
            if not isinstance(stores, dict):
                continue

            normalized_stores: dict[str, str] = {}
            for store_name, product_ref in stores.items():
                store_text = clean_text(store_name)
                product_text = clean_text(product_ref)
                if store_text and product_text:
                    normalized_stores[store_text] = product_text

            if len(normalized_stores) < 2:
                continue

            signature = tuple(sorted(normalized_stores.items()))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            unique_rows.append(
                {
                    "product_name": clean_text(row.get("product_name", "")),
                    "stores": normalized_stores,
                }
            )

        return unique_rows

    def load_prioritized_manual_rows(
        self,
        output_path: Path,
        store_columns: list[str],
        signature: str,
    ) -> list[dict[str, object]] | None:
        self.ensure_priority_relations_location()
        self.ensure_manual_comparisons_loaded()

        merged_rows: list[dict[str, object]] = []

        priority_rows = self.load_manual_rows_from_excel(PRIORITY_RELATIONS_FILE, store_columns)
        if priority_rows is not None:
            self.log_output.append(
                f"[INFO] Priority relations loaded ({PRIORITY_RELATIONS_FILE.name}): "
                f"{len(priority_rows)} row(s)"
            )
            merged_rows.extend(priority_rows)

        output_rows = self.load_manual_rows_from_excel(output_path, store_columns)
        if output_rows is not None:
            self.log_output.append(
                f"[INFO] Relations loaded from output Excel: {len(output_rows)} row(s)"
            )
            merged_rows.extend(output_rows)

        saved_rows = self.manual_comparisons.get(signature)
        if saved_rows:
            self.log_output.append(
                f"[INFO] Saved manual comparisons loaded: {len(saved_rows)} row(s)"
            )
            merged_rows.extend(saved_rows)

        deduplicated_rows = self._deduplicate_manual_rows(merged_rows)
        return deduplicated_rows or None

    def save_relations_to_excel(
        self,
        output_path: Path,
        relations_df: pd.DataFrame,
        store_columns: list[str],
    ) -> None:
        standard_relations_df = relations_df_to_standard(relations_df, store_columns)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            with pd.ExcelWriter(
                output_path,
                engine="openpyxl",
                mode="a",
                if_sheet_exists="replace",
            ) as writer:
                standard_relations_df.to_excel(writer, index=False, sheet_name="Relations")
        else:
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                standard_relations_df.to_excel(writer, index=False, sheet_name="Relations")

    def parse_entries_for_editor(
        self,
        named_entries: list[tuple[ListingEntry, str]],
    ) -> dict[str, object]:
        from ..pdf_parser import parse_listing_pdf_with_meta

        parsed_frames = {}
        for entry, store_name in named_entries:
            try:
                parsed_df, source_format = parse_listing_pdf_with_meta(entry.pdf_path)
                parsed_frames[store_name] = parsed_df
                self.log_output.append(
                    f"[OK] {store_name}: {entry.pdf_path.name} "
                    f"({len(parsed_df)} products, format: {source_format})"
                )
            except Exception as exc:
                self.log_output.append(f"[ERROR] {entry.pdf_path.name}: {exc}")

        if not parsed_frames:
            raise RuntimeError("No valid PDF could be processed.")

        return parsed_frames

    def _store_columns_for_relations_import(self) -> list[str]:
        entries = self.collect_entries()
        existing_entries = [entry for entry in entries if entry.pdf_path.exists()]
        if not existing_entries:
            return list(DEFAULT_STORE_NAMES)
        named_entries = self.build_named_entries(existing_entries)
        return [store_name for _, store_name in named_entries]

    def download_relations_sheet(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            QMessageBox.information(
                self,
                "Conversion in progress",
                "Wait until the current conversion ends before exporting relations.",
            )
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Download Relations Sheet",
            str(self.downloads_dir / "relations.xlsx"),
            "Excel files (*.xlsx)",
        )
        if not save_path:
            return

        target_path = Path(save_path)
        if target_path.suffix.lower() != ".xlsx":
            target_path = target_path.with_suffix(".xlsx")

        entries = self.collect_entries()
        if not entries:
            self.ensure_priority_relations_location()
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if PRIORITY_RELATIONS_FILE.exists():
                    copy2(PRIORITY_RELATIONS_FILE, target_path)
                else:
                    template_df = pd.DataFrame(
                        columns=["COMMON NAME", "SYSCO", "KOHL", "US FOODS"]
                    )
                    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
                        template_df.to_excel(writer, index=False, sheet_name="Relations")
            except OSError as exc:
                QMessageBox.warning(self, "Warning", f"Could not export relations sheet:\n{exc}")
                self.log_output.append(f"[WARN] Could not export relations sheet: {exc}")
                return

            self.log_output.append(f"[INFO] Relations sheet exported: {target_path}")
            QMessageBox.information(
                self,
                "Done",
                f"Relations sheet exported:\n{target_path}",
            )
            return

        if not self.validate_entries(entries):
            return

        named_entries = self.build_named_entries(entries)
        signature = self.build_comparison_signature(named_entries)
        output_path = self.build_output_path()
        store_names = [store_name for _, store_name in named_entries]
        manual_rows = self.load_prioritized_manual_rows(
            output_path=output_path,
            store_columns=store_names,
            signature=signature,
        )

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            parsed_frames = self.parse_entries_for_editor(named_entries)
            from ..comparison_engine import build_comparison_bundle

            bundle = build_comparison_bundle(
                frames_by_store=parsed_frames,
                manual_rows=manual_rows,
            )
            standard_relations_df = relations_df_to_standard(
                bundle["relations_df"],
                bundle["store_columns"],
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
                standard_relations_df.to_excel(writer, index=False, sheet_name="Relations")
        except Exception as exc:
            QMessageBox.warning(self, "Warning", f"Could not export relations sheet:\n{exc}")
            self.log_output.append(f"[ERROR] {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.log_output.append(f"[INFO] Relations sheet exported: {target_path}")
        QMessageBox.information(
            self,
            "Done",
            f"Relations sheet exported:\n{target_path}",
        )

    def load_relations_sheet(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            QMessageBox.information(
                self,
                "Conversion in progress",
                "Wait until the current conversion ends before loading relations.",
            )
            return

        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Relations Sheet",
            str(self.downloads_dir),
            "Excel files (*.xlsx *.xlsm *.xls)",
        )
        if not selected_path:
            return

        source_path = Path(selected_path)
        store_columns = self._store_columns_for_relations_import()
        manual_rows = self.load_manual_rows_from_excel(source_path, store_columns)
        if manual_rows is None:
            QMessageBox.warning(
                self,
                "Invalid file",
                "Could not read relations from the selected file.",
            )
            return

        try:
            PRIORITY_RELATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            if source_path.resolve() != PRIORITY_RELATIONS_FILE.resolve():
                copy2(source_path, PRIORITY_RELATIONS_FILE)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Warning",
                f"Could not load relations sheet:\n{exc}",
            )
            self.log_output.append(f"[WARN] Could not load relations sheet: {exc}")
            return

        self.log_output.append(
            f"[INFO] Priority relations loaded ({PRIORITY_RELATIONS_FILE.name}): {len(manual_rows)} row(s)"
        )
        QMessageBox.information(
            self,
            "Done",
            f"Relations sheet loaded:\n{PRIORITY_RELATIONS_FILE}",
        )

    def start_conversion(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            QMessageBox.information(
                self,
                "Conversion in progress",
                "A comparison is already running. Please wait until it finishes.",
            )
            return

        entries = self.collect_entries()
        if not self.validate_entries(entries):
            return

        named_entries = self.build_named_entries(entries)
        signature = self.build_comparison_signature(named_entries)
        output_path = self.build_output_path()
        store_names = [store_name for _, store_name in named_entries]
        manual_rows = self.load_prioritized_manual_rows(
            output_path=output_path,
            store_columns=store_names,
            signature=signature,
        )

        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(entries))
        self.progress_label.setText(f"Progress: 0/{len(entries)}")
        self.log_output.append("-" * 48)
        self.log_output.append(f"Starting comparison for {len(entries)} listing(s)...")
        if manual_rows:
            self.log_output.append(
                f"[INFO] Applying prioritized relations/manual overrides: {len(manual_rows)} row(s)"
            )

        from ..conversion_worker import ConversionWorker

        self.pending_result = None
        self.thread = QThread(self)
        self.worker = ConversionWorker(
            entries=entries,
            output_path=output_path,
            manual_rows=manual_rows,
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.on_log)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.on_thread_finished)
        self.thread.finished.connect(self.thread.deleteLater)

        self.set_controls_enabled(False)
        self.thread.start()

    def on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)
        self.progress_label.setText(f"Progress: {done}/{total}")

    def on_log(self, message: str) -> None:
        self.log_output.append(message)

    def on_worker_finished(self, result: dict) -> None:
        self.pending_result = result

    def on_thread_finished(self) -> None:
        self.set_controls_enabled(True)

        result = self.pending_result or {"ok": False, "error": "Conversion ended unexpectedly."}
        if result.get("ok"):
            summary = (
                f"Done. Stores: {result['store_count']} | "
                f"Products: {result['product_count']}"
            )
            self.log_output.append(summary)
            QMessageBox.information(
                self,
                "Process completed",
                summary + f"\n\nFile: {result['output_path']}",
            )
        else:
            error = result.get("error", "Unknown error")
            self.log_output.append(f"[ERROR] {error}")
            QMessageBox.critical(self, "Error", error)

        self.worker = None
        self.thread = None
        self.pending_result = None
