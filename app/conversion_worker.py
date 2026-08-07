from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtCore import QObject, Signal

from .comparison_engine import build_comparison_bundle
from .models import ListingEntry
from .pdf_parser import parse_listing_pdf_with_meta
from .config import FUZZY_MATCH_THRESHOLD
from .relations_sheet import relations_df_to_standard
from .reporting import (
    build_ranking_dataframe,
    export_report,
)
from .utils import ensure_unique_names


class ConversionWorker(QObject):
    progress = Signal(int, int)
    log = Signal(str)
    finished = Signal(dict)

    def __init__(
        self,
        entries: list[ListingEntry],
        output_path: Path,
        manual_rows: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__()
        self.entries = entries
        self.output_path = output_path
        self.manual_rows = manual_rows

    def run(self) -> None:
        result = {
            "ok": False,
            "output_path": str(self.output_path),
            "store_count": len(self.entries),
            "product_count": 0,
            "error": "",
        }

        try:
            unique_names = ensure_unique_names([entry.list_name for entry in self.entries])
            if unique_names != [entry.list_name for entry in self.entries]:
                self.log.emit(
                    "[INFO] Some listing names were duplicated. Added suffixes _2, _3..."
                )

            parsed_frames: dict[str, pd.DataFrame] = {}
            total = len(self.entries)

            for idx, (entry, store_name) in enumerate(zip(self.entries, unique_names), start=1):
                try:
                    if not entry.pdf_path.exists():
                        raise FileNotFoundError(f"File not found: {entry.pdf_path}")

                    parsed_df, source_format = parse_listing_pdf_with_meta(entry.pdf_path)
                    parsed_frames[store_name] = parsed_df
                    self.log.emit(
                        f"[OK] {store_name}: {entry.pdf_path.name} "
                        f"({len(parsed_df)} products, format: {source_format})"
                    )
                except Exception as exc:
                    self.log.emit(f"[ERROR] {entry.pdf_path.name}: {exc}")
                finally:
                    self.progress.emit(idx, total)

            if not parsed_frames:
                raise RuntimeError("No valid PDF could be processed.")

            self.log.emit(
                f"[INFO] Product matching: fuzzy similarity (threshold={FUZZY_MATCH_THRESHOLD:.2f})"
            )
            if self.manual_rows:
                self.log.emit(
                    f"[INFO] Manual comparison rows loaded: {len(self.manual_rows)}"
                )
            bundle = build_comparison_bundle(
                frames_by_store=parsed_frames,
                manual_rows=self.manual_rows,
            )
            comparison_df = bundle["comparison_df"]
            store_columns = list(parsed_frames.keys())
            relations_df = relations_df_to_standard(bundle["relations_df"], store_columns)
            ranking_df = build_ranking_dataframe(comparison_df, store_columns)

            export_report(
                output_path=self.output_path,
                comparison_df=comparison_df,
                ranking_df=ranking_df,
                store_columns=store_columns,
                relations_df=relations_df,
            )

            result["ok"] = True
            result["product_count"] = len(comparison_df)
            self.log.emit(f"[OK] Excel generated: {self.output_path}")

        except Exception as exc:
            result["error"] = str(exc)
            self.log.emit(f"[ERROR] {exc}")

        self.finished.emit(result)
