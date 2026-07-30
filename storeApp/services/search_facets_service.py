"""
Search facet aggregation + versioned cache for GET /api/store/search/.

Replaces the legacy dynamic-filters API for storefront sidebar facets.
"""
from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q

from storeApp.services.country_normalize import normalize_country_label

CACHE_PREFIX = "store_search_facets"
CACHE_TIMEOUT = getattr(settings, "SEARCH_FACETS_CACHE_TTL", 3600)
CACHE_VERSION_KEY = f"{CACHE_PREFIX}:version"

MAX_ATTRIBUTE_GROUPS = getattr(settings, "SEARCH_FACETS_MAX_ATTRIBUTE_GROUPS", 12)
MAX_OPTIONS_PER_ATTRIBUTE = getattr(settings, "SEARCH_FACETS_MAX_OPTIONS_PER_ATTRIBUTE", 30)

PRICE_RANGE_FILTER_Q = {
    "under_100k": Q(price_value__lt=100000),
    "100k_300k": Q(price_value__gte=100000, price_value__lt=300000),
    "300k_500k": Q(price_value__gte=300000, price_value__lt=500000),
    "over_500k": Q(price_value__gte=500000),
}


class SearchFacetsService:
    """Build and cache search response facets (brand, origin, attrs, price, stock, category)."""

    CACHE_VERSION_KEY = CACHE_VERSION_KEY

    @staticmethod
    def _cache_version() -> int:
        return cache.get(CACHE_VERSION_KEY) or 1

    @staticmethod
    def _cache_key(facet_params: dict) -> str:
        payload = json.dumps(facet_params, sort_keys=True, default=str)
        digest = hashlib.md5(payload.encode()).hexdigest()[:16]
        version = SearchFacetsService._cache_version()
        return f"{CACHE_PREFIX}:v{version}:{digest}"

    @staticmethod
    def invalidate_all_cache() -> None:
        version = SearchFacetsService._cache_version()
        cache.set(CACHE_VERSION_KEY, version + 1, timeout=None)

    @staticmethod
    def facet_params_from_request(
        *,
        query_normalized: str,
        category,
        brand,
        price_range,
        in_stock,
        origin_country=None,
        attrs=None,
    ) -> dict:
        return {
            "q": query_normalized,
            "category": str(category) if category not in (None, "") else None,
            "brand": str(brand) if brand not in (None, "") else None,
            "price_range": price_range or None,
            "in_stock": in_stock,
            "origin_country": str(origin_country) if origin_country not in (None, "") else None,
            "attrs": attrs or None,
        }

    @staticmethod
    def get_facets(queryset, facet_params: dict, *, use_cache: bool = True) -> dict:
        if use_cache:
            cache_key = SearchFacetsService._cache_key(facet_params)
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        include_category = not facet_params.get("category")
        facets = SearchFacetsService.build_facets(queryset, include_category=include_category)

        if use_cache:
            cache.set(cache_key, facets, timeout=CACHE_TIMEOUT)
        return facets

    @staticmethod
    def build_scalar_facets(queryset) -> dict:
        aggregated = queryset.aggregate(
            under_100k=Count("id", filter=PRICE_RANGE_FILTER_Q["under_100k"]),
            range_100k_300k=Count("id", filter=PRICE_RANGE_FILTER_Q["100k_300k"]),
            range_300k_500k=Count("id", filter=PRICE_RANGE_FILTER_Q["300k_500k"]),
            over_500k=Count("id", filter=PRICE_RANGE_FILTER_Q["over_500k"]),
            in_stock_count=Count("id", filter=Q(in_stock__gt=0)),
            out_of_stock_count=Count("id", filter=Q(in_stock__lte=0)),
        )
        return {
            "price_ranges": [
                {"key": "under_100k", "count": aggregated["under_100k"]},
                {"key": "100k_300k", "count": aggregated["range_100k_300k"]},
                {"key": "300k_500k", "count": aggregated["range_300k_500k"]},
                {"key": "over_500k", "count": aggregated["over_500k"]},
            ],
            "in_stock": [
                {"key": True, "count": aggregated["in_stock_count"]},
                {"key": False, "count": aggregated["out_of_stock_count"]},
            ],
        }

    @staticmethod
    def build_origin_country_facets(queryset) -> list[dict]:
        rows = (
            queryset.exclude(product__brand__country__isnull=True)
            .exclude(product__brand__country="")
            .values("product__brand__country")
            .annotate(count=Count("product_id", distinct=True))
            .order_by("-count", "product__brand__country")
        )
        merged: dict[str, int] = {}
        for item in rows:
            raw = item["product__brand__country"]
            canonical = normalize_country_label(raw)
            if not canonical:
                continue
            merged[canonical] = merged.get(canonical, 0) + int(item["count"] or 0)

        return [
            {"key": country, "name": country, "count": count}
            for country, count in sorted(merged.items(), key=lambda pair: (-pair[1], pair[0]))
        ]

    @staticmethod
    def build_attribute_facets(queryset) -> list[dict]:
        """
        Aggregate ProductAttributeValue on products in the variant queryset.

        Only attributes with count > 0 appear. Caps groups/options to keep payload small.
        """
        rows = (
            queryset.filter(
                product__attribute_values__option__attribute__is_filterable=True,
                product__attribute_values__option__attribute__active=True,
                product__attribute_values__option__active=True,
                product__attribute_values__active=True,
            )
            .values(
                "product__attribute_values__option__attribute__code",
                "product__attribute_values__option__attribute__label",
                "product__attribute_values__option__attribute__facet_type",
                "product__attribute_values__option__attribute__sort_order",
                "product__attribute_values__option__slug",
                "product__attribute_values__option__label",
            )
            .annotate(count=Count("product_id", distinct=True))
            .order_by(
                "product__attribute_values__option__attribute__sort_order",
                "-count",
                "product__attribute_values__option__label",
            )
        )

        grouped: dict[str, dict] = {}
        for item in rows:
            code = item["product__attribute_values__option__attribute__code"]
            slug = item["product__attribute_values__option__slug"]
            if not code or not slug:
                continue
            count = int(item["count"] or 0)
            if count <= 0:
                continue
            group = grouped.get(code)
            if group is None:
                group = {
                    "code": code,
                    "label": item["product__attribute_values__option__attribute__label"],
                    "type": item["product__attribute_values__option__attribute__facet_type"]
                    or "multiple",
                    "sort_order": item["product__attribute_values__option__attribute__sort_order"]
                    or 100,
                    "options": [],
                }
                grouped[code] = group
            if len(group["options"]) >= MAX_OPTIONS_PER_ATTRIBUTE:
                continue
            group["options"].append(
                {
                    "slug": slug,
                    "label": item["product__attribute_values__option__label"] or slug,
                    "count": count,
                }
            )

        groups = sorted(grouped.values(), key=lambda g: (g["sort_order"], g["code"]))
        trimmed = groups[:MAX_ATTRIBUTE_GROUPS]
        for group in trimmed:
            group.pop("sort_order", None)
        return trimmed

    @staticmethod
    def build_facets(queryset, *, include_category: bool = True) -> dict:
        scalar_facets = SearchFacetsService.build_scalar_facets(queryset)

        brand_facets = (
            queryset.exclude(product__brand_id__isnull=True)
            .values("product__brand_id", "product__brand__name")
            .annotate(count=Count("product_id", distinct=True))
            .order_by("-count", "product__brand__name")
        )

        result = {
            "brand": [
                {
                    "id": item["product__brand_id"],
                    "name": item["product__brand__name"],
                    "count": item["count"],
                }
                for item in brand_facets
                if item["product__brand_id"] is not None
            ],
            "origin_country": SearchFacetsService.build_origin_country_facets(queryset),
            "attributes": SearchFacetsService.build_attribute_facets(queryset),
            "price_ranges": scalar_facets["price_ranges"],
            "in_stock": scalar_facets["in_stock"],
        }

        if not include_category:
            result["category"] = []
            return result

        category_facets = (
            queryset.values(
                "product__categories__id",
                "product__categories__name",
                "product__categories__path_slug",
                "product__categories__slug",
            )
            .annotate(count=Count("product_id", distinct=True))
            .order_by("-count", "product__categories__name")
        )
        result["category"] = [
            {
                "id": item["product__categories__id"],
                "name": item["product__categories__name"],
                "slug": item["product__categories__path_slug"]
                or item["product__categories__slug"],
                "count": item["count"],
            }
            for item in category_facets
            if item["product__categories__id"] is not None
        ]
        return result
