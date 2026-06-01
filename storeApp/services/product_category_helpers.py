"""Helpers for ProductCategory M2M (filters, voucher context, counts)."""
from __future__ import annotations

from django.conf import settings
from django.db.models import Exists, OuterRef

from storeApp.models import Category, Product, ProductCategory, ProductVariant


def store_db_alias(using=None) -> str:
    if using:
        return using
    return "store" if "store" in settings.DATABASES else "default"


def category_slug_tokens(category) -> set[str]:
    """path_slug and slug for voucher / filter matching."""
    if not category:
        return set()
    tokens = set()
    path = (getattr(category, "path_slug", None) or "").strip()
    slug = (getattr(category, "slug", None) or "").strip()
    if path:
        tokens.add(path)
    if slug:
        tokens.add(slug)
    return tokens


def collect_category_slugs_for_product(product: Product | None) -> set[str]:
    """All category path/slug tokens from M2M; fallback to primary FK."""
    slugs: set[str] = set()
    if not product or not getattr(product, "pk", None):
        return slugs

    if "product_categories" in getattr(product, "_prefetched_objects_cache", {}):
        links = product.product_categories.all()
    else:
        links = product.product_categories.select_related("category").order_by(
            "-is_primary", "sort_order", "category_id"
        )

    for pc in links:
        slugs.update(category_slug_tokens(pc.category))

    if not slugs:
        slugs.update(category_slug_tokens(getattr(product, "category", None)))

    return slugs


def category_tree_ids(category: Category, *, using=None) -> list[int]:
    """Category id + all active descendants by path_slug prefix."""
    db = store_db_alias(using)
    category_path_slug = category.path_slug or category.slug
    ids = {category.id}
    if category_path_slug:
        sub_ids = (
            Category.objects.using(db)
            .filter(active=True, path_slug__istartswith=f"{category_path_slug}/")
            .values_list("id", flat=True)
        )
        ids.update(sub_ids)
    return list(ids)


def product_in_categories_exists(category_ids, *, using=None):
    """Exists subquery: variant's product has ProductCategory in category_ids."""
    db = store_db_alias(using)
    ids = list(category_ids)
    if not ids:
        return Exists(ProductCategory.objects.none())
    return Exists(
        ProductCategory.objects.using(db).filter(
            product_id=OuterRef("product_id"),
            category_id__in=ids,
        )
    )


def count_variants_in_category_ids(category_ids, *, using=None) -> int:
    db = store_db_alias(using)
    return (
        ProductVariant.objects.using(db)
        .filter(active=True, is_published=True)
        .filter(product_in_categories_exists(category_ids, using=db))
        .distinct()
        .count()
    )


def count_distinct_products_in_category_ids(category_ids, *, using=None) -> int:
    """Distinct active products in category tree (M2M), for UI productCount."""
    db = store_db_alias(using)
    return (
        ProductVariant.objects.using(db)
        .filter(active=True, is_published=True, product__active=True)
        .filter(product_in_categories_exists(category_ids, using=db))
        .values("product_id")
        .distinct()
        .count()
    )
