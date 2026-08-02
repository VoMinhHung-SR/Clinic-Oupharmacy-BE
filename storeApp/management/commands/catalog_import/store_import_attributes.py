"""
Import product filter attributes → CatalogAttributeOption + ProductAttributeValue.

Idempotent get_or_create options/values from a catalog import row.
Requires CatalogAttribute dictionary (seed_catalog_attributes) to exist.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from storeApp.models import CatalogAttribute, CatalogAttributeOption, ProductAttributeValue
from storeApp.services.catalog_attribute_map import (
    FLAT_ATTR_KEYS,
    SOURCE_ATTR_SKIP,
    SOURCE_TO_STORE_ATTR,
)

from .store_import_row import parse_json_field


def attribute_option_slug(label: str) -> str:
    """ASCII slug for option labels (Vietnamese-friendly)."""
    if not label:
        return ""
    text = unicodedata.normalize("NFKD", str(label).strip())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d").replace("Đ", "d").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:120]


def _as_label_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                label = (
                    item.get("label")
                    or item.get("name")
                    or item.get("attributeName")
                    or item.get("value")
                )
                if label:
                    out.append(str(label).strip())
            elif item is not None and str(item).strip():
                out.append(str(item).strip())
        return out
    if isinstance(raw, dict):
        label = raw.get("label") or raw.get("name") or raw.get("attributeName") or raw.get("value")
        return [str(label).strip()] if label else []
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        # Only attempt JSON when the string looks like a serialized list/object/string.
        if stripped[0] in "[{'\"":
            parsed = parse_json_field(stripped, default=None)
            if isinstance(parsed, (list, dict)):
                return _as_label_list(parsed)
            if isinstance(parsed, str) and parsed.strip():
                return [parsed.strip()]
        return [stripped]
    return [str(raw).strip()] if str(raw).strip() else []


def _resolve_store_code(source_key: str) -> Optional[str]:
    key = (source_key or "").strip()
    if not key or key in SOURCE_ATTR_SKIP:
        return None
    # attributes.objectUse → objectUse
    if "." in key:
        key = key.split(".")[-1]
    if key in SOURCE_ATTR_SKIP:
        return None
    return SOURCE_TO_STORE_ATTR.get(key)


def collect_attribute_labels_from_row(row: dict) -> dict[str, list[str]]:
    """
    Return {store_attr_code: [labels...]} from a flattened catalog import row.

    Accepts nested `attributes` object and/or flat product fields.
    """
    collected: dict[str, list[str]] = {}

    def add(store_code: str, labels: list[str]) -> None:
        if not store_code or not labels:
            return
        bucket = collected.setdefault(store_code, [])
        for label in labels:
            if label and label not in bucket:
                bucket.append(label)

    # Nested attributes blob (preferred catalog enrichment)
    for blob_key in ("attributes", "product.attributes"):
        blob = row.get(blob_key)
        if blob is None:
            continue
        if isinstance(blob, str):
            blob = parse_json_field(blob, default={})
        if not isinstance(blob, dict):
            continue
        for source_key, raw in blob.items():
            store_code = _resolve_store_code(str(source_key))
            if store_code:
                add(store_code, _as_label_list(raw))

    # Flat keys
    for flat_key in FLAT_ATTR_KEYS:
        if flat_key in ("attributes", "product.attributes"):
            continue
        if flat_key not in row or row.get(flat_key) in (None, ""):
            continue
        store_code = _resolve_store_code(flat_key)
        if store_code:
            add(store_code, _as_label_list(row.get(flat_key)))

    return collected


def upsert_product_attributes_from_row(
    product,
    row: dict,
    *,
    dry_run: bool = False,
    using: str = "store",
) -> dict:
    """
    Attach ProductAttributeValue rows for one product.

    Creates missing CatalogAttributeOption labels under known CatalogAttribute codes.
    Does not delete prior values (additive skeleton).
    """
    stats = {
        "attribute_values_created": 0,
        "attribute_values_existing": 0,
        "attribute_options_created": 0,
        "attribute_codes_skipped_missing_dict": 0,
    }
    if product is None:
        return stats

    by_code = collect_attribute_labels_from_row(row)
    if not by_code:
        return stats

    attr_cache = {
        a.code: a
        for a in CatalogAttribute.objects.using(using).filter(
            code__in=list(by_code.keys()), active=True, is_filterable=True
        )
    }

    for store_code, labels in by_code.items():
        attr = attr_cache.get(store_code)
        if attr is None:
            stats["attribute_codes_skipped_missing_dict"] += 1
            continue

        for label in labels:
            slug = attribute_option_slug(label)
            if not slug:
                continue
            if dry_run:
                exists = (
                    CatalogAttributeOption.objects.using(using)
                    .filter(attribute=attr, slug=slug)
                    .exists()
                )
                if not exists:
                    stats["attribute_options_created"] += 1
                stats["attribute_values_created"] += 1
                continue

            option, opt_created = CatalogAttributeOption.objects.using(using).get_or_create(
                attribute=attr,
                slug=slug,
                defaults={"label": label[:160], "active": True},
            )
            if opt_created:
                stats["attribute_options_created"] += 1
            elif option.label != label and label:
                # Keep first label; do not thrash on alternate spellings.
                pass

            _pav, pav_created = ProductAttributeValue.objects.using(using).get_or_create(
                product=product,
                option=option,
                defaults={"active": True},
            )
            if pav_created:
                stats["attribute_values_created"] += 1
            else:
                stats["attribute_values_existing"] += 1

    return stats
