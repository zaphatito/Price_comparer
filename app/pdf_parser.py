from __future__ import annotations

import re
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd
import pdfplumber

from .utils import clean_text, normalize_key, to_numeric


def _build_line_text(items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    previous_end: float | None = None
    for item in sorted(items, key=lambda entry: float(entry["x"])):
        text = clean_text(item.get("text", ""))
        if not text:
            continue
        if parts and previous_end is not None and float(item["x"]) - previous_end > 1.5:
            parts.append(" ")
        parts.append(text)
        previous_end = float(item["end_x"])
    return clean_text("".join(parts))


def _page_lines(page: Any) -> list[dict[str, Any]]:
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        keep_blank_chars=False,
        use_text_flow=False,
    ) or []
    fragments = [
        {
            "text": clean_text(word.get("text", "")),
            "x": float(word.get("x0", 0)),
            "end_x": float(word.get("x1", word.get("x0", 0))),
            "y": float(word.get("bottom", word.get("top", 0))),
        }
        for word in words
        if clean_text(word.get("text", ""))
    ]
    fragments.sort(key=lambda item: (float(item["y"]), float(item["x"])))

    lines: list[dict[str, Any]] = []
    for fragment in fragments:
        target = next(
            (
                line
                for line in lines
                if abs(float(line["y"]) - float(fragment["y"])) <= 2.5
            ),
            None,
        )
        normalized = {
            "text": fragment["text"],
            "x": fragment["x"],
            "end_x": fragment["end_x"],
        }
        if target is None:
            lines.append({"y": fragment["y"], "items": [normalized]})
        else:
            target["items"].append(normalized)

    output: list[dict[str, Any]] = []
    for line in lines:
        word_items = sorted(line["items"], key=lambda item: float(item["x"]))
        ordered_items: list[dict[str, Any]] = []
        for item in word_items:
            if (
                ordered_items
                and float(item["x"]) - float(ordered_items[-1]["end_x"]) <= 6
            ):
                ordered_items[-1]["text"] = clean_text(
                    f'{ordered_items[-1]["text"]} {item["text"]}'
                )
                ordered_items[-1]["end_x"] = item["end_x"]
            else:
                ordered_items.append(dict(item))
        text = _build_line_text(ordered_items)
        if text:
            output.append({"y": line["y"], "items": ordered_items, "text": text})
    return output


def _merge_header_cells(line: dict[str, Any]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for item in sorted(line["items"], key=lambda entry: float(entry["x"])):
        if cells and float(item["x"]) - float(cells[-1]["end_x"]) <= 8:
            cells[-1]["text"] = clean_text(f'{cells[-1]["text"]} {item["text"]}')
            cells[-1]["end_x"] = item["end_x"]
        else:
            cells.append(
                {
                    "text": item["text"],
                    "x": item["x"],
                    "end_x": item["end_x"],
                    "y": line["y"],
                }
            )
    return cells


def _is_product_header(text: str) -> bool:
    normalized = normalize_key(text)
    return (
        "product description" in normalized
        or "product name" in normalized
        or normalized == "description"
        or normalized == "item description"
    )


def _is_price_header(text: str) -> bool:
    normalized = normalize_key(text)
    return "price" in normalized or "cost" in normalized


def _find_tabular_header(
    lines: list[dict[str, Any]], page_height: float
) -> dict[str, float | None] | None:
    search_limit = page_height * 0.48
    product_candidates: list[dict[str, Any]] = []
    price_candidates: list[dict[str, Any]] = []
    cells_by_line: list[list[dict[str, Any]]] = []

    for line_index, line in enumerate(lines):
        cells = _merge_header_cells(line)
        cells_by_line.append(cells)
        if float(line["y"]) > search_limit:
            continue
        for cell in cells:
            candidate = {**cell, "line_index": line_index}
            if _is_product_header(str(cell["text"])):
                product_candidates.append(candidate)
            if _is_price_header(str(cell["text"])):
                price_candidates.append(candidate)

    best_pair: dict[str, Any] | None = None
    for product in product_candidates:
        for price in price_candidates:
            vertical_distance = abs(float(product["y"]) - float(price["y"]))
            if float(product["x"]) >= float(price["x"]) or vertical_distance > 32:
                continue
            score = vertical_distance + abs(
                int(product["line_index"]) - int(price["line_index"])
            ) * 3
            if best_pair is None or score < float(best_pair["score"]):
                best_pair = {"product": product, "price": price, "score": score}

    if best_pair is None:
        return None

    product = best_pair["product"]
    price = best_pair["price"]
    center_y = (float(product["y"]) + float(price["y"])) / 2
    header_items = [
        cell
        for cells in cells_by_line
        for cell in cells
        if abs(float(cell["y"]) - center_y) <= 8
    ]
    previous_candidates = [
        item for item in header_items if float(item["end_x"]) < float(product["x"])
    ]
    previous = max(previous_candidates, key=lambda item: float(item["end_x"]), default=None)
    next_candidates = [
        item
        for item in header_items
        if float(item["x"]) > float(product["end_x"]) + 8
    ]
    next_item = min(next_candidates, key=lambda item: float(item["x"]), default=None)
    after_price_candidates = [
        item
        for item in header_items
        if float(item["x"]) > float(price["end_x"]) + 8
    ]
    after_price = min(
        after_price_candidates, key=lambda item: float(item["x"]), default=None
    )

    pack_header = min(
        (
            item
            for item in header_items
            if "pack" in normalize_key(str(item["text"]))
        ),
        key=lambda item: float(item["x"]),
        default=None,
    )
    product_id_header = next(
        (
            item
            for item in header_items
            if "upc" in normalize_key(str(item["text"]))
        ),
        None,
    )
    if product_id_header is None:
        product_id_header = next(
            (
                item
                for item in header_items
                if normalize_key(str(item["text"])) == "item"
            ),
            None,
        )
    if product_id_header is None:
        product_id_header = next(
            (
                item
                for item in header_items
                if "#" in str(item["text"])
                and "product" in normalize_key(str(item["text"]))
            ),
            None,
        )

    def column_bounds(header_item: dict[str, Any] | None) -> tuple[float | None, float | None]:
        if header_item is None:
            return None, None
        before = max(
            (
                item
                for item in header_items
                if float(item["end_x"]) < float(header_item["x"])
            ),
            key=lambda item: float(item["end_x"]),
            default=None,
        )
        after = min(
            (
                item
                for item in header_items
                if float(item["x"]) > float(header_item["end_x"])
            ),
            key=lambda item: float(item["x"]),
            default=None,
        )
        start = (
            (float(before["end_x"]) + float(header_item["x"])) / 2
            if before is not None
            else max(0, float(header_item["x"]) - 40)
        )
        end = (
            (float(header_item["end_x"]) + float(after["x"])) / 2
            if after is not None
            else float("inf")
        )
        return start, end

    pack_start, pack_end = column_bounds(pack_header)
    product_id_start, product_id_end = column_bounds(product_id_header)

    return {
        "header_bottom": max(float(item["y"]) for item in header_items) + 4,
        "product_start": (
            float(previous["end_x"]) + 4
            if previous is not None
            else max(0, float(product["x"]) - 40)
        ),
        "product_end": (
            (float(product["end_x"]) + float(next_item["x"])) / 2
            if next_item is not None
            else float(price["x"]) - 24
        ),
        "price_start": float(price["x"]) - 32,
        "price_end": (
            float(after_price["x"]) - 6 if after_price is not None else float("inf")
        ),
        "pack_start": pack_start,
        "pack_end": pack_end,
        "product_id_start": product_id_start,
        "product_id_end": product_id_end,
    }


def _parse_price_candidate(text: str) -> tuple[float, str] | None:
    cleaned = clean_text(text).replace(",", "")
    unit_match = re.search(
        r"\$?\s*(-?\d{1,5}(?:\.\d+)?)\s*/?\s*(CS|EA|LB|CT|PK|BX|BG|RL|DZ)\b",
        cleaned,
        flags=re.IGNORECASE,
    )
    if unit_match:
        return float(unit_match.group(1)), unit_match.group(2).upper()
    currency_match = re.search(r"\$\s*(-?\d{1,5}(?:\.\d+)?)", cleaned)
    if currency_match:
        return float(currency_match.group(1)), ""
    plain_match = re.fullmatch(r"\s*(-?\d{1,5}(?:\.\d+)?)\s*", cleaned)
    if plain_match:
        return float(plain_match.group(1)), ""
    return None


def _column_text_near_row(
    lines: list[dict[str, Any]],
    row_y: float,
    row_window: float,
    start: float | None,
    end: float | None,
) -> str:
    if start is None or end is None:
        return ""
    items = [
        {"text": item["text"], "x": item["x"], "y": line["y"]}
        for line in lines
        if abs(float(line["y"]) - row_y) <= row_window
        for item in line["items"]
        if float(item["x"]) >= start and float(item["x"]) < end
    ]
    items.sort(key=lambda item: (float(item["y"]), float(item["x"])))
    return clean_text(" ".join(str(item["text"]) for item in items))


def _prefer_case_prices(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = clean_text(record.get("product_id", "")) or (
            f'{normalize_key(record.get("product_name", ""))}|'
            f'{normalize_key(record.get("pack_size", ""))}'
        )
        current = grouped.get(key)
        is_case = record.get("price_unit") == "CS"
        current_is_case = current is not None and current.get("price_unit") == "CS"
        if current is None or (is_case and not current_is_case):
            grouped[key] = record
    return list(grouped.values())


def _disambiguate_duplicate_names(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(normalize_key(record.get("product_name", "")), []).append(record)

    output: list[dict[str, Any]] = []
    for group in grouped.values():
        if len(group) == 1:
            output.append(group[0])
            continue

        qualifiers: list[str] = []
        for record in group:
            pack = re.sub(r"^1\s+(?=\S)", "", clean_text(record.get("pack_size", "")))
            qualifiers.append(pack or f'Item {clean_text(record.get("product_id", ""))}')

        for record, raw_qualifier in zip(group, qualifiers):
            qualifier = raw_qualifier
            product_id = clean_text(record.get("product_id", ""))
            if qualifiers.count(raw_qualifier) > 1 and product_id:
                qualifier = f"{qualifier} · {product_id}"
            output.append(
                {
                    **record,
                    "product_name": f'{clean_text(record.get("product_name", ""))} [{qualifier}]',
                }
            )
    return output


def _group_positioned_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    valid: list[dict[str, Any]] = []
    for record in records:
        product_name = clean_text(record.get("product_name", ""))
        product_key = normalize_key(product_name)
        raw_price = record.get("price")
        price = None if raw_price is None or pd.isna(raw_price) else float(raw_price)
        if not product_name or not product_key or (price is not None and price <= 0):
            continue
        valid.append(
            {"product_key": product_key, "product_name": product_name, "price": price}
        )

    valid.sort(
        key=lambda item: (
            str(item["product_key"]),
            item["price"] is None,
            float(item["price"]) if item["price"] is not None else float("inf"),
            str(item["product_name"]),
        )
    )
    grouped: dict[str, dict[str, Any]] = {}
    for item in valid:
        current = grouped.get(str(item["product_key"]))
        if current is None or (
            current["price"] is None and item["price"] is not None
        ) or (
            current["price"] is not None
            and item["price"] is not None
            and float(item["price"]) < float(current["price"])
        ):
            grouped[str(item["product_key"])] = item
    return pd.DataFrame(
        list(grouped.values()), columns=["product_key", "product_name", "price"]
    )


def extract_positioned_candidate_rows(pdf_path: Path) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            lines = _page_lines(page)
            header = _find_tabular_header(lines, float(page.height))
            if header is None:
                continue
            data_lines = [
                line for line in lines if float(line["y"]) > float(header["header_bottom"])
            ]
            price_rows: list[dict[str, Any]] = []
            for line in data_lines:
                price_text = " ".join(
                    str(item["text"])
                    for item in line["items"]
                    if float(item["x"]) >= float(header["price_start"])
                    and float(item["x"]) < float(header["price_end"])
                )
                parsed_price = _parse_price_candidate(price_text)
                if parsed_price is not None and parsed_price[0] > 0:
                    price_rows.append(
                        {"price": parsed_price[0], "unit": parsed_price[1], "y": line["y"]}
                    )
                elif "no price" in normalize_key(price_text):
                    price_rows.append({"price": None, "unit": "", "y": line["y"]})

            row_gaps = [
                float(price_rows[index]["y"]) - float(price_rows[index - 1]["y"])
                for index in range(1, len(price_rows))
                if float(price_rows[index]["y"]) - float(price_rows[index - 1]["y"]) > 4
            ]
            if row_gaps:
                gap_median = median(row_gaps)
                upper_gaps = [gap for gap in row_gaps if gap >= gap_median]
                typical_gap = median(upper_gaps) if upper_gaps else 0
            else:
                typical_gap = 0
            row_window = min(24, max(6, typical_gap * 0.45 if typical_gap else 12))

            for price_row in price_rows:
                product_items = [
                    {"text": item["text"], "x": item["x"], "y": line["y"]}
                    for line in data_lines
                    if abs(float(line["y"]) - float(price_row["y"])) <= row_window
                    for item in line["items"]
                    if float(item["x"]) >= float(header["product_start"])
                    and float(item["x"]) < float(header["product_end"])
                ]
                product_items.sort(
                    key=lambda item: (float(item["y"]), float(item["x"]))
                )
                product_name = clean_text(
                    " ".join(str(item["text"]) for item in product_items)
                )
                if not product_name:
                    continue
                pack_size = _column_text_near_row(
                    data_lines,
                    float(price_row["y"]),
                    row_window,
                    header["pack_start"],
                    header["pack_end"],
                )
                product_id_text = _column_text_near_row(
                    data_lines,
                    float(price_row["y"]),
                    row_window,
                    header["product_id_start"],
                    header["product_id_end"],
                )
                product_id_match = re.search(r"\b\d{5,8}\b", product_id_text)
                records.append(
                    {
                        "product_name": product_name,
                        "price": price_row["price"],
                        "price_unit": price_row["unit"],
                        "pack_size": pack_size,
                        "product_id": product_id_match.group(0) if product_id_match else "",
                    }
                )

    preferred = _prefer_case_prices(records)
    disambiguated = _disambiguate_duplicate_names(preferred)
    return _group_positioned_records(disambiguated)


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
    parsed = extract_positioned_candidate_rows(pdf_path)
    source_format = "tabular"
    if parsed.empty:
        parsed = extract_tabular_candidate_rows(pdf_path)
    if parsed.empty:
        parsed = extract_single_column_candidate_rows(pdf_path)
        source_format = "single-column"

    parsed = parsed[parsed["product_name"] != ""].copy()
    parsed["product_key"] = parsed["product_name"].map(normalize_key)
    parsed = parsed[parsed["product_key"] != ""]

    if parsed.empty:
        raise ValueError("No valid products were found in this PDF format.")

    records = _group_positioned_records(
        parsed[["product_name", "price"]].to_dict(orient="records")
    )
    return records, source_format


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
