from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber

from .utils import clean_text, normalize_key, to_numeric


def normalize_table_rows(table: list[list[object]]) -> list[list[str]]:
    rows: list[list[str]] = []
    max_cols = 0
    for raw_row in table:
        if raw_row is None:
            continue
        row = [clean_text(col) for col in raw_row]
        if not any(row):
            continue
        rows.append(row)
        max_cols = max(max_cols, len(row))

    if max_cols == 0:
        return []

    normalized_rows: list[list[str]] = []
    for row in rows:
        if len(row) < max_cols:
            row = row + [""] * (max_cols - len(row))
        elif len(row) > max_cols:
            row = row[:max_cols]
        normalized_rows.append(row)
    return normalized_rows


def header_row_score(row: list[str]) -> int:
    joined = " ".join(normalize_key(cell) for cell in row if cell)
    if not joined:
        return -999

    score = 0
    if any(word in joined for word in ("product", "description", "item", "name", "line")):
        score += 4
    if "price" in joined or "cost" in joined:
        score += 4
    if any(word in joined for word in ("qty", "pack", "size", "brand")):
        score += 1
    if re.search(r"\d", joined):
        score -= 1
    return score


def find_header_row_index(rows: list[list[str]]) -> int | None:
    if not rows:
        return None
    best_idx = -1
    best_score = -999
    for idx, row in enumerate(rows[:8]):
        score = header_row_score(row)
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_score < 4:
        return None
    return best_idx


def table_to_dataframe(table: list[list[object]]) -> pd.DataFrame | None:
    rows = normalize_table_rows(table)
    if not rows:
        return None
    if len(rows[0]) == 1:
        return None

    header_idx = find_header_row_index(rows)
    if header_idx is None:
        return None

    raw_header = rows[header_idx]
    columns: list[str] = []
    used_names: dict[str, int] = {}
    for col_idx, raw_name in enumerate(raw_header, start=1):
        base_name = clean_text(raw_name) or f"col_{col_idx}"
        count = used_names.get(base_name, 0) + 1
        used_names[base_name] = count
        columns.append(base_name if count == 1 else f"{base_name}_{count}")

    data_rows: list[list[str]] = []
    for row in rows[header_idx + 1 :]:
        if row == raw_header:
            continue
        if sum(1 for col in row if col) <= 1:
            continue
        data_rows.append(row[: len(columns)])

    if not data_rows:
        return None
    return pd.DataFrame(data_rows, columns=columns)


def detect_product_and_price_columns(columns: list[str]) -> tuple[str, str]:
    product_col = ""
    product_score = -999
    price_col = ""
    price_score = -999

    for col in columns:
        normalized = normalize_key(col)
        p_score = 0
        if "product" in normalized:
            p_score += 6
        if "name" in normalized:
            p_score += 4
        if "description" in normalized:
            p_score += 3
        if "item" in normalized:
            p_score += 2
        if "price" in normalized or "cost" in normalized or "qty" in normalized:
            p_score -= 3
        if p_score > product_score:
            product_score = p_score
            product_col = col

        r_score = 0
        if "price" in normalized:
            r_score += 7
        if "cost" in normalized:
            r_score += 5
        if "unit" in normalized:
            r_score += 2
        if "total" in normalized:
            r_score -= 3
        if "qty" in normalized:
            r_score -= 2
        if r_score > price_score:
            price_score = r_score
            price_col = col

    if product_score <= 0:
        raise ValueError(f"Could not detect product column. Columns: {columns}")
    if price_score <= 0:
        raise ValueError(f"Could not detect price column. Columns: {columns}")

    return product_col, price_col


def extract_tabular_candidate_rows(pdf_path: Path) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                table_df = table_to_dataframe(table)
                if table_df is None or table_df.empty:
                    continue
                try:
                    product_col, price_col = detect_product_and_price_columns(
                        list(table_df.columns)
                    )
                except ValueError:
                    continue

                parsed = pd.DataFrame()
                parsed["product_name"] = table_df[product_col].map(clean_text)
                parsed["price"] = to_numeric(table_df[price_col])
                parsed = parsed[(parsed["product_name"] != "") & parsed["price"].notna()]
                if not parsed.empty:
                    parts.append(parsed[["product_name", "price"]])

    if not parts:
        return pd.DataFrame(columns=["product_name", "price"])
    return pd.concat(parts, ignore_index=True)


def parse_single_column_line(line: str) -> dict[str, object] | None:
    text = clean_text(line)
    if not text:
        return None
    if not re.match(r"^\d{4,}\b", text):
        return None
    normalized = normalize_key(text)
    if "item pack pack size" in normalized:
        return None

    price_match = re.search(
        r"\$?(\d{1,5}(?:,\d{3})*(?:\.\d+)?)\s*(?:CS|EA|LB|CT|PK|BX|BG|RL|DZ)\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if not price_match:
        return None

    try:
        price = float(price_match.group(1).replace(",", ""))
    except ValueError:
        return None

    left_text = text[: price_match.start()].strip()
    left_text = re.sub(r"[_-]+\s*$", "", left_text).strip()
    tokens = left_text.split()
    if len(tokens) < 4:
        return None

    tail_tokens = tokens[3:]
    if len(tail_tokens) >= 2:
        product_tokens = tail_tokens[1:]
    else:
        product_tokens = tail_tokens

    product_name = clean_text(" ".join(product_tokens))
    if not product_name:
        return None

    return {"product_name": product_name, "price": price}


def extract_single_column_candidate_rows(pdf_path: Path) -> pd.DataFrame:
    records: list[dict[str, object]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                rows = normalize_table_rows(table)
                if not rows:
                    continue
                if len(rows[0]) != 1:
                    continue
                for row in rows:
                    parsed = parse_single_column_line(row[0])
                    if parsed is not None:
                        records.append(parsed)

            if records:
                continue

            page_text = page.extract_text() or ""
            for line in page_text.splitlines():
                parsed = parse_single_column_line(line)
                if parsed is not None:
                    records.append(parsed)

    if not records:
        return pd.DataFrame(columns=["product_name", "price"])

    return pd.DataFrame(records, columns=["product_name", "price"])


def parse_listing_pdf_with_meta(pdf_path: Path) -> tuple[pd.DataFrame, str]:
    parsed = extract_tabular_candidate_rows(pdf_path)
    source_format = "tabular"
    if parsed.empty:
        parsed = extract_single_column_candidate_rows(pdf_path)
        source_format = "single-column"

    parsed = parsed[(parsed["product_name"] != "") & parsed["price"].notna()]
    parsed["product_key"] = parsed["product_name"].map(normalize_key)
    parsed = parsed[parsed["product_key"] != ""]

    if parsed.empty:
        raise ValueError(
            "No valid products with price were found in this PDF format."
        )

    parsed = parsed.sort_values(["product_key", "price", "product_name"])
    grouped = parsed.groupby("product_key", as_index=False).agg(
        product_name=("product_name", "first"),
        price=("price", "min"),
    )
    return grouped, source_format


def parse_listing_pdf(pdf_path: Path) -> pd.DataFrame:
    grouped, _ = parse_listing_pdf_with_meta(pdf_path)
    return grouped


def detect_provider_name_from_text(raw_text: str) -> str | None:
    text = normalize_key(raw_text)
    if not text:
        return None
    if "kohl" in text:
        return "KOHL"
    if "us foods" in text or "us food" in text or "usfoods" in text:
        return "US FOOD"
    if "sysco" in text:
        return "SYSCO"
    return None


def detect_provider_name_from_pdf(pdf_path: Path) -> str:
    from_name = detect_provider_name_from_text(pdf_path.name)
    if from_name is not None:
        return from_name

    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_to_check = min(2, len(pdf.pages))
            for page_idx in range(pages_to_check):
                page_text = pdf.pages[page_idx].extract_text() or ""
                detected = detect_provider_name_from_text(page_text[:4000])
                if detected is not None:
                    return detected
    except Exception:
        pass

    return "SYSCO"
