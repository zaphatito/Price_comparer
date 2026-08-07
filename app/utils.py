from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def get_downloads_dir() -> Path:
    home = Path.home()
    candidates: list[Path] = []

    env_user = os.environ.get("USERPROFILE")
    if env_user:
        user_path = Path(env_user)
        candidates.append(user_path / "Downloads")
        candidates.append(user_path / "Descargas")

    one_drive = os.environ.get("OneDrive")
    if one_drive:
        one_drive_path = Path(one_drive)
        candidates.append(one_drive_path / "Downloads")
        candidates.append(one_drive_path / "Descargas")

    candidates.append(home / "Downloads")
    candidates.append(home / "Descargas")

    for path in candidates:
        if path.exists():
            return path

    fallback = home / "Downloads"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(text: str) -> str:
    # Keep letters when accents are present (for example, "camaron" with accent marks).
    ascii_text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    lowered = ascii_text.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def to_numeric(series: pd.Series) -> pd.Series:
    import pandas as pd

    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.extract(r"(-?\d+(?:\.\d+)?)", expand=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def ensure_unique_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for raw_name in names:
        base = clean_text(raw_name) or "listing"
        count = seen.get(base, 0) + 1
        seen[base] = count
        if count == 1:
            result.append(base)
        else:
            result.append(f"{base}_{count}")
    return result
