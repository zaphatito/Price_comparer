from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache

import pandas as pd

from .config import FUZZY_MATCH_AMBIGUITY_MARGIN, FUZZY_MATCH_THRESHOLD
from .utils import clean_text, normalize_key

TOKEN_NORMALIZATION_MAP = {
    # Spanish -> English food terms
    "aceite": "oil",
    "aguacate": "avocado",
    "aluminio": "aluminum",
    "amarilla": "yellow",
    "amarillo": "yellow",
    "arroz": "rice",
    "azucar": "sugar",
    "blanca": "white",
    "blanco": "white",
    "blanqueador": "bleach",
    "bolsa": "bag",
    "camaron": "shrimp",
    "camarones": "shrimp",
    "carne": "meat",
    "cebolla": "onion",
    "cerdo": "pork",
    "champinon": "mushroom",
    "chile": "pepper",
    "costilla": "rib",
    "crudo": "raw",
    "cruda": "raw",
    "desinfectante": "disinfectant",
    "enlatada": "canned",
    "enlatado": "canned",
    "entera": "whole",
    "entero": "whole",
    "espuma": "foam",
    "fresca": "fresh",
    "fresco": "fresh",
    "frijol": "bean",
    "hueso": "bone",
    "huevo": "egg",
    "jalapeno": "jalapeno",
    "leche": "milk",
    "limon": "lime",
    "manteca": "shortening",
    "margarina": "margarine",
    "mezcla": "mix",
    "molida": "ground",
    "muslo": "thigh",
    "papel": "paper",
    "pechuga": "breast",
    "pimiento": "pepper",
    "pollo": "chicken",
    "queso": "cheese",
    "recipiente": "container",
    "res": "beef",
    "rebanada": "sliced",
    "rebanado": "sliced",
    "roja": "red",
    "rojo": "red",
    "sal": "salt",
    "salmuera": "canned",
    "servilleta": "napkin",
    "surtidos": "mixed",
    "tallos": "stem",
    "tapa": "lid",
    "tilapia": "tilapia",
    "tomate": "tomato",
    "tomatillo": "tomatillo",
    "vegetales": "vegetable",
    "verde": "green",
    "vaso": "cup",
    "vaca": "beef",
    "alum": "aluminum",
    "brst": "breast",
    "brgr": "burger",
    "bnsls": "boneless",
    "bnsl": "boneless",
    "chix": "chicken",
    "cmpt": "compartment",
    "cmp": "compartment",
    "comp": "compartment",
    "cont": "container",
    "ctn": "carton",
    "dsp": "dispenser",
    "frsh": "fresh",
    "frzn": "frozen",
    "grnd": "ground",
    "nugg": "nugget",
    "pk": "pack",
    "oz": "ounce",
    "lbs": "pound",
    "lb": "pound",
    "pty": "patty",
    "stk": "steak",
    "wht": "white",
    "ylw": "yellow",
    "xmlt": "melting",
    "ez": "easy",
}

STATE_TOKEN_MAP = {
    "fresh": "fresh",
    "frozen": "frozen",
    "canned": "canned",
    "iqf": "frozen",
}

CONFLICTING_STATE_PAIRS = {
    frozenset(("fresh", "canned")),
    frozenset(("fresh", "frozen")),
}

GENERIC_TOKENS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "without",
    "al",
    "con",
    "de",
    "del",
    "el",
    "en",
    "la",
    "las",
    "los",
    "o",
    "para",
    "por",
    "sin",
    "y",
    "anaquel",
    "case",
    "caja",
    "estables",
    "estable",
    "grade",
    "liquida",
    "liquido",
    "pack",
    "ref",
    "seleccion",
    "selecto",
    "suelto",
    "tipo",
    "unidad",
    "unidades",
    "units",
    "fresh",
    "frozen",
    "raw",
    "whole",
    "mixed",
    "special",
}

CATEGORY_KEYWORDS = {
    "beef": {
        "beef",
        "ribeye",
        "burger",
        "patty",
        "steak",
        "chub",
        "ground",
        "namp",
    },
    "pork": {"pork", "ham", "bacon", "rib", "shoulder", "butt"},
    "chicken": {"chicken", "breast", "thigh", "nugget", "wing"},
    "seafood": {"shrimp", "tilapia", "fish", "salmon", "tuna"},
    "produce": {
        "avocado",
        "onion",
        "tomato",
        "tomatillo",
        "jalapeno",
        "cilantro",
        "pepper",
        "lime",
        "mushroom",
        "vegetable",
        "bean",
        "rice",
    },
    "dairy": {"cheese", "milk", "margarine", "butter", "cream"},
    "paper": {"paper", "napkin", "bag", "towel"},
    "container": {"container", "compartment", "foam", "aluminum", "cup", "lid", "tray"},
    "cleaning": {"bleach", "disinfectant", "soap", "detergent"},
}

_CATEGORY_BY_TOKEN: dict[str, set[str]] = {}
for category, tokens in CATEGORY_KEYWORDS.items():
    for token in tokens:
        _CATEGORY_BY_TOKEN.setdefault(token, set()).add(category)


@dataclass(frozen=True)
class ProductFeatures:
    canonical_text: str
    token_set: frozenset[str]
    strong_tokens: frozenset[str]
    number_tokens: frozenset[str]
    categories: frozenset[str]
    states: frozenset[str]


def _singularize_token(token: str) -> str:
    if len(token) > 5 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


@lru_cache(maxsize=16384)
def product_features(product_name: str) -> ProductFeatures:
    normalized = normalize_key(product_name)
    tokens: list[str] = []
    categories: set[str] = set()
    states: set[str] = set()

    for raw_token in normalized.split():
        mapped = TOKEN_NORMALIZATION_MAP.get(raw_token, raw_token)
        for token in mapped.split():
            token = _singularize_token(token)
            state = STATE_TOKEN_MAP.get(token)
            if state is not None:
                states.add(state)
            if token in GENERIC_TOKENS:
                continue
            tokens.append(token)
            categories.update(_CATEGORY_BY_TOKEN.get(token, set()))

    canonical_text = " ".join(tokens)
    token_set = frozenset(tokens)
    strong_tokens = frozenset(
        token for token in tokens if len(token) >= 4 and not any(ch.isdigit() for ch in token)
    )
    number_tokens = frozenset(token for token in tokens if any(ch.isdigit() for ch in token))
    return ProductFeatures(
        canonical_text=canonical_text,
        token_set=token_set,
        strong_tokens=strong_tokens,
        number_tokens=number_tokens,
        categories=frozenset(categories),
        states=frozenset(states),
    )


def _has_state_conflict(states_a: frozenset[str], states_b: frozenset[str]) -> bool:
    if not states_a or not states_b:
        return False
    for state_a in states_a:
        for state_b in states_b:
            if state_a == state_b:
                continue
            if frozenset((state_a, state_b)) in CONFLICTING_STATE_PAIRS:
                return True
    return False


@lru_cache(maxsize=32768)
def product_similarity(name_a: str, name_b: str) -> float:
    features_a = product_features(name_a)
    features_b = product_features(name_b)

    if not features_a.token_set or not features_b.token_set:
        return 0.0
    if _has_state_conflict(features_a.states, features_b.states):
        return 0.0

    shared_tokens = features_a.token_set & features_b.token_set
    shared_strong = features_a.strong_tokens & features_b.strong_tokens
    shared_numbers = features_a.number_tokens & features_b.number_tokens

    # Hard guard against unrelated products that only share noise.
    if not shared_strong and len(shared_tokens) < 2:
        seq_guard = SequenceMatcher(None, features_a.canonical_text, features_b.canonical_text).ratio()
        if seq_guard < 0.78:
            return 0.0

    # Numeric mismatch is a strong indicator for pack-size mismatch.
    if features_a.number_tokens and features_b.number_tokens and not shared_numbers:
        return 0.0

    union_size = len(features_a.token_set | features_b.token_set)
    overlap = len(shared_tokens)
    jaccard = overlap / union_size if union_size else 0.0
    containment = overlap / min(len(features_a.token_set), len(features_b.token_set))
    sequence_ratio = SequenceMatcher(None, features_a.canonical_text, features_b.canonical_text).ratio()
    strong_overlap = len(shared_strong) / max(1, min(len(features_a.strong_tokens), len(features_b.strong_tokens)))

    score = 0.44 * max(jaccard, containment) + 0.30 * sequence_ratio + 0.26 * strong_overlap

    if shared_numbers:
        score += 0.07

    if features_a.categories and features_b.categories:
        if features_a.categories & features_b.categories:
            score += 0.05
        else:
            score -= 0.22

    return max(0.0, min(1.0, score))


def _frame_items(frame: pd.DataFrame) -> list[dict[str, object]]:
    data = frame[["product_key", "product_name", "price"]].copy()
    data = data.dropna(subset=["product_key", "product_name", "price"])
    data["product_key"] = data["product_key"].map(lambda value: clean_text(value).lower())
    data["product_name"] = data["product_name"].map(clean_text)
    data = data[(data["product_key"] != "") & (data["product_name"] != "")]
    data["price"] = pd.to_numeric(data["price"], errors="coerce")
    data = data.dropna(subset=["price"])
    data["price"] = data["price"].astype(float)
    data = data.sort_values(["product_key", "price", "product_name"], kind="stable")
    grouped = data.groupby("product_key", as_index=False).agg(
        product_name=("product_name", "first"),
        price=("price", "min"),
    )
    return [
        {
            "product_key": str(row.product_key),
            "product_name": str(row.product_name),
            "price": float(row.price),
        }
        for row in grouped.itertuples(index=False)
    ]


def _cluster_display_name(cluster: dict[str, object]) -> str:
    items_by_store: dict[str, dict[str, object]] = cluster["items_by_store"]
    candidates = [str(item["product_name"]) for item in items_by_store.values() if item.get("product_name")]
    current = clean_text(cluster.get("product_name", ""))
    if current:
        candidates.append(current)
    if not candidates:
        return "UNNAMED PRODUCT"
    candidates = sorted(set(candidates), key=lambda value: (len(value), value.lower()))
    return candidates[0]


def _upsert_cluster_item(
    cluster: dict[str, object],
    store_name: str,
    item: dict[str, object],
    score: float,
    source: str,
) -> None:
    items_by_store: dict[str, dict[str, object]] = cluster["items_by_store"]
    items_by_store[store_name] = {
        "product_key": str(item["product_key"]),
        "product_name": str(item["product_name"]),
        "price": float(item["price"]),
        "score": float(score),
        "source": source,
    }
    if source == "manual":
        cluster["source"] = "manual"
    cluster["product_name"] = _cluster_display_name(cluster)


def _new_cluster(
    store_name: str,
    item: dict[str, object],
    source: str,
    score: float = 1.0,
    product_name: str | None = None,
) -> dict[str, object]:
    cluster = {
        "product_name": clean_text(product_name) if product_name else str(item["product_name"]),
        "source": source,
        "items_by_store": {},
    }
    _upsert_cluster_item(cluster, store_name, item, score=score, source=source)
    return cluster


def _cluster_similarity(product_name: str, cluster: dict[str, object]) -> float:
    items_by_store: dict[str, dict[str, object]] = cluster["items_by_store"]
    if not items_by_store:
        return 0.0
    return max(
        product_similarity(product_name, str(entry["product_name"]))
        for entry in items_by_store.values()
    )


def _best_cluster_for_item(
    item: dict[str, object],
    clusters: list[dict[str, object]],
    store_name: str,
) -> tuple[int, float, float]:
    best_idx = -1
    best_score = 0.0
    second_score = 0.0
    product_key = str(item["product_key"])
    product_name = str(item["product_name"])

    for idx, cluster in enumerate(clusters):
        items_by_store: dict[str, dict[str, object]] = cluster["items_by_store"]
        if store_name in items_by_store:
            continue

        if any(product_key == str(entry["product_key"]) for entry in items_by_store.values()):
            return idx, 1.0, 0.0

        score = _cluster_similarity(product_name, cluster)
        if score > best_score:
            second_score = best_score
            best_score = score
            best_idx = idx
        elif score > second_score:
            second_score = score

    return best_idx, best_score, second_score


def _assign_store_items_to_clusters(
    clusters: list[dict[str, object]],
    store_name: str,
    items: list[dict[str, object]],
    threshold: float,
    ambiguity_margin: float,
) -> tuple[set[int], set[int]]:
    eligible_candidates: list[tuple[float, int, int]] = []
    for item_idx, item in enumerate(items):
        cluster_idx, best_score, second_score = _best_cluster_for_item(
            item=item,
            clusters=clusters,
            store_name=store_name,
        )
        if cluster_idx < 0:
            continue
        if best_score < threshold:
            continue
        if (best_score - second_score) < ambiguity_margin:
            continue
        eligible_candidates.append((best_score, item_idx, cluster_idx))

    eligible_candidates.sort(reverse=True, key=lambda value: value[0])
    used_item_idx: set[int] = set()
    used_cluster_idx: set[int] = set()
    assigned_item_idx: set[int] = set()

    for score, item_idx, cluster_idx in eligible_candidates:
        if item_idx in used_item_idx or cluster_idx in used_cluster_idx:
            continue
        used_item_idx.add(item_idx)
        used_cluster_idx.add(cluster_idx)
        assigned_item_idx.add(item_idx)
        _upsert_cluster_item(
            cluster=clusters[cluster_idx],
            store_name=store_name,
            item=items[item_idx],
            score=score,
            source="auto",
        )

    unassigned_item_idx = set(range(len(items))) - assigned_item_idx
    return assigned_item_idx, unassigned_item_idx


def _store_lookup_tables(
    items_by_store: dict[str, list[dict[str, object]]],
) -> tuple[dict[str, dict[str, dict[str, object]]], dict[str, dict[str, dict[str, object]]]]:
    by_key: dict[str, dict[str, dict[str, object]]] = {}
    by_name: dict[str, dict[str, dict[str, object]]] = {}
    for store_name, items in items_by_store.items():
        by_key[store_name] = {}
        by_name[store_name] = {}
        for item in items:
            key = str(item["product_key"])
            by_key[store_name][key] = item
            normalized_name = normalize_key(str(item["product_name"]))
            if normalized_name and normalized_name not in by_name[store_name]:
                by_name[store_name][normalized_name] = item
    return by_key, by_name


def _resolve_manual_item(
    store_name: str,
    ref_value: object,
    lookup_by_key: dict[str, dict[str, dict[str, object]]],
    lookup_by_name: dict[str, dict[str, dict[str, object]]],
) -> dict[str, object] | None:
    ref_text = clean_text(ref_value)
    if not ref_text:
        return None

    by_key = lookup_by_key.get(store_name, {})
    by_name = lookup_by_name.get(store_name, {})

    if ref_text in by_key:
        return by_key[ref_text]

    normalized = normalize_key(ref_text)
    if normalized in by_name:
        return by_name[normalized]

    return None


def _apply_manual_rows(
    clusters: list[dict[str, object]],
    used_keys_by_store: dict[str, set[str]],
    manual_rows: list[dict[str, object]],
    lookup_by_key: dict[str, dict[str, dict[str, object]]],
    lookup_by_name: dict[str, dict[str, dict[str, object]]],
) -> None:
    for raw_row in manual_rows:
        stores = raw_row.get("stores")
        if not isinstance(stores, dict):
            continue

        product_name = clean_text(raw_row.get("product_name", ""))
        cluster = {
            "product_name": product_name,
            "source": "manual",
            "items_by_store": {},
        }

        for store_name, ref_value in stores.items():
            item = _resolve_manual_item(
                store_name=store_name,
                ref_value=ref_value,
                lookup_by_key=lookup_by_key,
                lookup_by_name=lookup_by_name,
            )
            if item is None:
                continue

            product_key = str(item["product_key"])
            if product_key in used_keys_by_store.get(store_name, set()):
                continue

            _upsert_cluster_item(
                cluster=cluster,
                store_name=store_name,
                item=item,
                score=1.0,
                source="manual",
            )
            used_keys_by_store[store_name].add(product_key)

        if cluster["items_by_store"]:
            cluster["product_name"] = _cluster_display_name(cluster)
            clusters.append(cluster)


def build_store_catalog(
    frames_by_store: dict[str, pd.DataFrame],
) -> dict[str, list[dict[str, object]]]:
    ordered_store_names = list(frames_by_store.keys())
    if not ordered_store_names:
        raise ValueError("Listings could not be combined.")
    return {store_name: _frame_items(frames_by_store[store_name]) for store_name in ordered_store_names}


def _clusters_to_rows(
    clusters: list[dict[str, object]],
    store_names: list[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    comparison_rows: list[dict[str, object]] = []
    relation_rows: list[dict[str, object]] = []
    relations_sheet_rows: list[dict[str, object]] = []

    sorted_clusters = sorted(clusters, key=lambda cluster: normalize_key(_cluster_display_name(cluster)))

    for row_idx, cluster in enumerate(sorted_clusters, start=1):
        product_name = _cluster_display_name(cluster)
        product_key = normalize_key(product_name) or f"cluster_{row_idx}"
        source = str(cluster.get("source", "auto"))
        items_by_store: dict[str, dict[str, object]] = cluster["items_by_store"]

        comparison_row: dict[str, object] = {
            "product_key": product_key,
            "Product": product_name,
        }
        relation_row: dict[str, object] = {
            "product_name": product_name,
            "source": source,
            "stores": {},
        }
        relations_sheet_row: dict[str, object] = {
            "Product": product_name,
            "Match Source": source,
        }

        for store_name in store_names:
            item = items_by_store.get(store_name)
            if item is None:
                comparison_row[store_name] = None
                relation_row["stores"][store_name] = None
                relations_sheet_row[f"{store_name} Product"] = None
                relations_sheet_row[f"{store_name} Price"] = None
                relations_sheet_row[f"{store_name} Score"] = None
                continue

            product_value = str(item["product_name"])
            price_value = float(item["price"])
            score_value = float(item["score"])

            comparison_row[store_name] = price_value
            relation_row["stores"][store_name] = {
                "product_key": str(item["product_key"]),
                "product_name": product_value,
                "price": price_value,
                "score": score_value,
                "source": str(item["source"]),
            }
            relations_sheet_row[f"{store_name} Product"] = product_value
            relations_sheet_row[f"{store_name} Price"] = price_value
            relations_sheet_row[f"{store_name} Score"] = round(score_value, 4)

        comparison_rows.append(comparison_row)
        relation_rows.append(relation_row)
        relations_sheet_rows.append(relations_sheet_row)

    return comparison_rows, relation_rows, relations_sheet_rows


def build_comparison_bundle(
    frames_by_store: dict[str, pd.DataFrame],
    manual_rows: list[dict[str, object]] | None = None,
    threshold: float | None = None,
    ambiguity_margin: float | None = None,
) -> dict[str, object]:
    ordered_store_names = list(frames_by_store.keys())
    if not ordered_store_names:
        raise ValueError("Listings could not be combined.")

    threshold_value = FUZZY_MATCH_THRESHOLD if threshold is None else float(threshold)
    ambiguity_value = (
        FUZZY_MATCH_AMBIGUITY_MARGIN if ambiguity_margin is None else float(ambiguity_margin)
    )

    items_by_store = build_store_catalog(frames_by_store)
    clusters: list[dict[str, object]] = []
    used_keys_by_store: dict[str, set[str]] = {store_name: set() for store_name in ordered_store_names}
    lookup_by_key, lookup_by_name = _store_lookup_tables(items_by_store)

    if manual_rows:
        _apply_manual_rows(
            clusters=clusters,
            used_keys_by_store=used_keys_by_store,
            manual_rows=manual_rows,
            lookup_by_key=lookup_by_key,
            lookup_by_name=lookup_by_name,
        )

    for store_name in ordered_store_names:
        remaining_items = [
            item
            for item in items_by_store[store_name]
            if str(item["product_key"]) not in used_keys_by_store[store_name]
        ]
        if not remaining_items:
            continue

        if not clusters:
            for item in remaining_items:
                clusters.append(_new_cluster(store_name=store_name, item=item, source="auto"))
                used_keys_by_store[store_name].add(str(item["product_key"]))
            continue

        _, unassigned_item_idx = _assign_store_items_to_clusters(
            clusters=clusters,
            store_name=store_name,
            items=remaining_items,
            threshold=threshold_value,
            ambiguity_margin=ambiguity_value,
        )

        for item_idx in sorted(unassigned_item_idx):
            item = remaining_items[item_idx]
            clusters.append(_new_cluster(store_name=store_name, item=item, source="auto"))
            used_keys_by_store[store_name].add(str(item["product_key"]))

        # Mark assigned items as used after assignment.
        for cluster in clusters:
            item = cluster["items_by_store"].get(store_name)
            if item is not None:
                used_keys_by_store[store_name].add(str(item["product_key"]))

    if not clusters:
        raise ValueError("Listings could not be combined.")

    comparison_rows, relation_rows, relations_sheet_rows = _clusters_to_rows(clusters, ordered_store_names)
    comparison_df = pd.DataFrame(comparison_rows)
    comparison_df = comparison_df[["product_key", "Product"] + ordered_store_names]
    comparison_df = comparison_df.sort_values("Product", kind="stable").reset_index(drop=True)

    relations_df = pd.DataFrame(relations_sheet_rows)
    relations_df = relations_df.sort_values("Product", kind="stable").reset_index(drop=True)

    return {
        "comparison_df": comparison_df,
        "relation_rows": relation_rows,
        "relations_df": relations_df,
        "store_columns": ordered_store_names,
    }


def build_comparison_dataframe(
    frames_by_store: dict[str, pd.DataFrame],
    manual_rows: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    bundle = build_comparison_bundle(frames_by_store=frames_by_store, manual_rows=manual_rows)
    return bundle["comparison_df"]
