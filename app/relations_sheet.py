from __future__ import annotations

import pandas as pd

from .utils import clean_text, normalize_key

PROVIDER_KEYS = ("sysco", "kohl", "usfood")
PROVIDER_COLUMN_BY_KEY = {
    "sysco": "nombre_sysco",
    "kohl": "nombre_kohl",
    "usfood": "nombre_usfood",
}
STANDARD_RELATIONS_COLUMNS = [
    "nombre_producto",
    "nombre_sysco",
    "nombre_kohl",
    "nombre_usfood",
]
RELATION_VALUE_PLACEHOLDERS = {
    "-",
    "--",
    "\u2014",
    "n/a",
    "na",
    "none",
    "null",
    "sin dato",
    "s/d",
}


def _normalize_relation_value(value: object) -> str:
    if pd.isna(value):
        return ""

    text = clean_text(value)
    if not text:
        return ""

    if text.casefold() in RELATION_VALUE_PLACEHOLDERS:
        return ""

    normalized = normalize_key(text)
    if not normalized:
        return ""

    return text


def provider_key_from_store_name(store_name: str) -> str | None:
    normalized = normalize_key(clean_text(store_name))
    if not normalized:
        return None

    tokens = set(normalized.split())
    if "sysco" in tokens or "sysco" in normalized:
        return "sysco"
    if "kohl" in tokens or "kohl" in normalized:
        return "kohl"
    if "usfoods" in tokens or ("us" in tokens and ("food" in tokens or "foods" in tokens)):
        return "usfood"
    return None


def build_store_provider_mapping(
    store_columns: list[str],
) -> tuple[dict[str, str], dict[str, str | None]]:
    store_to_provider: dict[str, str] = {}
    used_provider_keys: set[str] = set()

    for store_name in store_columns:
        provider_key = provider_key_from_store_name(store_name)
        if provider_key is None or provider_key in used_provider_keys:
            continue
        store_to_provider[store_name] = provider_key
        used_provider_keys.add(provider_key)

    remaining_provider_keys = [
        provider_key
        for provider_key in PROVIDER_KEYS
        if provider_key not in used_provider_keys
    ]
    for store_name in store_columns:
        if store_name in store_to_provider:
            continue
        if not remaining_provider_keys:
            break
        provider_key = remaining_provider_keys.pop(0)
        store_to_provider[store_name] = provider_key
        used_provider_keys.add(provider_key)

    provider_to_store: dict[str, str | None] = {provider_key: None for provider_key in PROVIDER_KEYS}
    for store_name, provider_key in store_to_provider.items():
        if provider_to_store.get(provider_key) is None:
            provider_to_store[provider_key] = store_name

    return store_to_provider, provider_to_store


def relations_df_to_standard(
    relations_df: pd.DataFrame,
    store_columns: list[str],
) -> pd.DataFrame:
    if relations_df.empty:
        return pd.DataFrame(columns=STANDARD_RELATIONS_COLUMNS)

    store_to_provider, _ = build_store_provider_mapping(store_columns)
    rows: list[dict[str, str]] = []

    for _, row in relations_df.iterrows():
        out_row = {column: "" for column in STANDARD_RELATIONS_COLUMNS}

        out_row["nombre_producto"] = _normalize_relation_value(row.get("Product", ""))

        for store_name in store_columns:
            source_column = f"{store_name} Product"
            if source_column not in relations_df.columns:
                continue
            provider_key = store_to_provider.get(store_name)
            if provider_key is None:
                continue

            provider_column = PROVIDER_COLUMN_BY_KEY[provider_key]
            value = row.get(source_column, "")
            product_name = _normalize_relation_value(value)
            if product_name:
                out_row[provider_column] = product_name

        if not out_row["nombre_producto"]:
            for provider_column in STANDARD_RELATIONS_COLUMNS[1:]:
                if out_row[provider_column]:
                    out_row["nombre_producto"] = out_row[provider_column]
                    break

        rows.append(out_row)

    return pd.DataFrame(rows, columns=STANDARD_RELATIONS_COLUMNS)


def _legacy_relations_df_to_manual_rows(
    relations_df: pd.DataFrame,
    store_columns: list[str],
) -> list[dict[str, object]]:
    product_columns = [f"{store_name} Product" for store_name in store_columns]
    for product_column in product_columns:
        if product_column not in relations_df.columns:
            return []

    manual_rows: list[dict[str, object]] = []
    for _, row in relations_df.iterrows():
        stores: dict[str, str] = {}
        for store_name, product_column in zip(store_columns, product_columns):
            value = row.get(product_column, "")
            product_name = _normalize_relation_value(value)
            if product_name:
                stores[store_name] = product_name

        if not stores:
            continue

        group_name = _normalize_relation_value(row.get("Product", ""))
        if not group_name:
            group_name = next(iter(stores.values()))

        manual_rows.append(
            {
                "product_name": group_name,
                "stores": stores,
            }
        )

    return manual_rows


def _find_provider_columns(relations_df: pd.DataFrame) -> dict[str, str]:
    provider_column_by_key: dict[str, str] = {}
    for column_name in relations_df.columns:
        provider_key = provider_key_from_store_name(str(column_name))
        if provider_key is None or provider_key in provider_column_by_key:
            continue
        provider_column_by_key[provider_key] = str(column_name)
    return provider_column_by_key


def _find_group_column(relations_df: pd.DataFrame) -> str | None:
    preferred_columns = (
        "nombre_producto",
        "COMMON NAME",
        "Common Name",
        "Product",
        "producto",
    )
    for column_name in preferred_columns:
        if column_name in relations_df.columns:
            return column_name

    allowed_names = {"common name", "nombre producto", "product", "producto"}
    for column_name in relations_df.columns:
        if normalize_key(str(column_name)) in allowed_names:
            return str(column_name)
    return None


def _provider_relations_df_to_manual_rows(
    relations_df: pd.DataFrame,
    store_columns: list[str],
) -> list[dict[str, object]]:
    provider_columns = _find_provider_columns(relations_df)
    if not provider_columns:
        return []

    _, provider_to_store = build_store_provider_mapping(store_columns)
    group_column = _find_group_column(relations_df)
    manual_rows: list[dict[str, object]] = []

    for _, row in relations_df.iterrows():
        stores: dict[str, str] = {}
        for provider_key, source_column in provider_columns.items():
            store_name = provider_to_store.get(provider_key)
            if not store_name:
                continue
            product_name = _normalize_relation_value(row.get(source_column, ""))
            if product_name:
                stores[store_name] = product_name

        if not stores:
            continue

        group_name = ""
        if group_column is not None:
            group_name = _normalize_relation_value(row.get(group_column, ""))
        if not group_name:
            group_name = next(iter(stores.values()))

        manual_rows.append(
            {
                "product_name": group_name,
                "stores": stores,
            }
        )

    return manual_rows


def relations_df_to_manual_rows(
    relations_df: pd.DataFrame,
    store_columns: list[str],
) -> list[dict[str, object]]:
    if relations_df.empty:
        return []

    if set(STANDARD_RELATIONS_COLUMNS).issubset(set(relations_df.columns)):
        _, provider_to_store = build_store_provider_mapping(store_columns)
        manual_rows: list[dict[str, object]] = []

        for _, row in relations_df.iterrows():
            stores: dict[str, str] = {}
            for provider_key in PROVIDER_KEYS:
                store_name = provider_to_store.get(provider_key)
                if not store_name:
                    continue
                provider_column = PROVIDER_COLUMN_BY_KEY[provider_key]
                value = row.get(provider_column, "")
                product_name = _normalize_relation_value(value)
                if product_name:
                    stores[store_name] = product_name

            if not stores:
                continue

            group_name = _normalize_relation_value(row.get("nombre_producto", ""))
            if not group_name:
                group_name = next(iter(stores.values()))

            manual_rows.append(
                {
                    "product_name": group_name,
                    "stores": stores,
                }
            )

        return manual_rows

    provider_manual_rows = _provider_relations_df_to_manual_rows(relations_df, store_columns)
    if provider_manual_rows:
        return provider_manual_rows

    return _legacy_relations_df_to_manual_rows(relations_df, store_columns)
