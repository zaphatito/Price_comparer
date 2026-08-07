from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ListingEntry:
    list_name: str
    pdf_path: Path
