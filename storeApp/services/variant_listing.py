"""Helpers: one representative ProductVariant row per Product for list/search cards."""
from __future__ import annotations

from django.db.models import Count, F, Q, QuerySet, Window
from django.db.models.functions import RowNumber


def annotate_variant_count(queryset: QuerySet, *, using: str = "store") -> QuerySet:
    return queryset.annotate(
        variant_count=Count(
            "product__variants",
            filter=Q(
                product__variants__active=True,
                product__variants__is_published=True,
            ),
        )
    )


def one_variant_per_product(
    queryset: QuerySet,
    *,
    partition_order,
) -> QuerySet:
    """Keep a single variant row per product_id (PostgreSQL window)."""
    return queryset.annotate(
        _variant_row=Window(
            expression=RowNumber(),
            partition_by=[F("product_id")],
            order_by=partition_order,
        )
    ).filter(_variant_row=1)


def count_distinct_products(queryset: QuerySet) -> int:
    return queryset.values("product_id").distinct().count()
