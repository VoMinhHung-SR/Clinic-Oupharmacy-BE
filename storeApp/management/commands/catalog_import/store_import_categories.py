"""Category tree resolution for catalog CSV/JSON import."""

from __future__ import annotations

from typing import Optional

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import Category

from .store_import_row import parse_json_field


def parse_category_array_from_row(row: dict) -> list:
    return parse_json_field(row.get("category.category", "[]"), default=[])


def resolve_leaf_category(
    category_array: list,
    cache: dict,
    using: str = STORE_DATABASE_ALIAS,
) -> tuple[Optional[Category], int]:
    """
    category_array: [{'name': '...', 'slug': '...'}, ...]
    Returns (leaf Category | None, number of new nodes added to cache).
    """
    if not category_array:
        return None, 0
    prev_len = len(cache)
    leaf = Category.get_or_create_from_array(category_array, cache=cache, using=using)
    return leaf, max(0, len(cache) - prev_len)
