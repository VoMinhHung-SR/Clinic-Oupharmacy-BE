"""
Resolve a store URL path to category listing or product detail (single source of truth for FE routing).
"""
from __future__ import annotations

from django.db import models
from django.db.models import Exists, OuterRef, Q

from storeApp.models import Category, Product, ProductCategory, ProductVariant


def resolve_store_path(path_slug: str, *, using: str = "store") -> dict:
    """
    Returns:
        page: "category" | "product" | "not_found"
        category_path: str (for list/filters or product context)
        product_slug: str | None
        product_id: int | None
        default_variant_id: int | None
    """
    normalized = (path_slug or "").strip().strip("/")
    if not normalized:
        return {"page": "not_found"}

    if "/" in normalized:
        parts = normalized.split("/")
        medicine_slug = parts[-1]
        cat_path_slug = "/".join(parts[:-1])

        product = (
            Product.objects.using(using)
            .filter(active=True, slug__iexact=medicine_slug)
            .first()
        )
        if product and cat_path_slug:
            category = (
                Category.objects.using(using)
                .filter(active=True)
                .filter(
                    Q(path_slug__iexact=cat_path_slug) | Q(slug__iexact=cat_path_slug)
                )
                .first()
            )
            if category:
                url_path = (category.path_slug or category.slug or "").strip()
                prefix = f"{url_path}/" if url_path else None
                m2m_match = Q(category_id=category.id)
                if prefix:
                    m2m_match |= Q(category__path_slug__istartswith=prefix)

                variant = (
                    ProductVariant.objects.using(using)
                    .filter(active=True, is_published=True, product=product)
                    .filter(
                        Exists(
                            ProductCategory.objects.using(using)
                            .filter(product_id=OuterRef("product_id"))
                            .filter(m2m_match)
                        )
                    )
                    .order_by("-product_ranking", "id")
                    .first()
                )
                if variant:
                    listed = category.path_slug or category.slug
                    return {
                        "page": "product",
                        "category_path": listed,
                        "product_slug": medicine_slug,
                        "product_id": product.id,
                        "default_variant_id": variant.id,
                    }

    category = (
        Category.objects.using(using)
        .filter(active=True)
        .filter(Q(path_slug__iexact=normalized) | Q(slug__iexact=normalized))
        .first()
    )
    if category:
        return {
            "page": "category",
            "category_path": category.path_slug or category.slug,
            "product_slug": None,
            "product_id": None,
            "default_variant_id": None,
        }

    return {"page": "not_found"}
