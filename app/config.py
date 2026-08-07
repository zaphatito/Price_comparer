from __future__ import annotations

from pathlib import Path

DEFAULT_STORE_NAMES = ["sysco", "us food", "kohls"]
DEFAULT_OUTPUT_FILE = "price_comparison.xlsx"
PROVIDER_NAME_PROMPT = "ENTER SUPPLIER NAME"
APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
VIEWS_DIR = APP_DIR / "views"
MAIN_WINDOW_VIEWS_DIR = VIEWS_DIR / "main_window"
COMPARISON_EDITOR_VIEWS_DIR = VIEWS_DIR / "comparison_editor"
MANUAL_COMPARISONS_FILE = APP_DIR / "manual_comparisons.json"
PRIORITY_RELATIONS_FILE = DATA_DIR / "relations.xlsx"
LEGACY_PRIORITY_RELATIONS_FILE = APP_DIR / "relations.xlsx"
FUZZY_MATCH_THRESHOLD = 0.50
FUZZY_MATCH_AMBIGUITY_MARGIN = 0.06
