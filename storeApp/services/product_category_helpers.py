"""Helpers for ProductCategory M2M (filters, voucher context, counts)."""
from __future__ import annotations

from django.conf import settings
from django.db.models import Exists, OuterRef, Q

from storeApp.models import Category, Product, ProductCategory, ProductVariant

# Cap BFS depth — store category tree is shallow (0→1→2).
_MAX_CATEGORY_TREE_DEPTH = 8


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
    """
    Category id + all active descendants.

    Uses parent_id BFS (reliable) with path_slug prefix as supplement when tree is sparse.
    """
    db = store_db_alias(using)
    ids: set[int] = {category.id}
    frontier = [category.id]

    for _ in range(_MAX_CATEGORY_TREE_DEPTH):
        child_ids = list(
            Category.objects.using(db)
            .filter(active=True, parent_id__in=frontier)
            .values_list("id", flat=True)
        )
        new_ids = [cid for cid in child_ids if cid not in ids]
        if not new_ids:
            break
        ids.update(new_ids)
        frontier = new_ids

    category_path_slug = (category.path_slug or category.slug or "").strip()
    if category_path_slug:
        path_ids = Category.objects.using(db).filter(
            active=True,
            path_slug__istartswith=f"{category_path_slug}/",
        ).values_list("id", flat=True)
        ids.update(path_ids)

    return list(ids)


def product_in_categories_q(category_ids, *, using=None) -> Q:
    """
    Q filter: variant's product is in any of category_ids via M2M **or** primary FK fallback.
    """
    db = store_db_alias(using)
    ids = list(category_ids)
    if not ids:
        return Q(pk__in=[])

    m2m_match = Exists(
        ProductCategory.objects.using(db).filter(
            product_id=OuterRef("product_id"),
            category_id__in=ids,
        )
    )
    fk_match = Q(product__category_id__in=ids)
    return Q(m2m_match) | fk_match


def product_in_categories_exists(category_ids, *, using=None):
    """Exists subquery wrapper — prefer product_in_categories_q for OR with FK."""
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


def filter_variants_by_category_id(queryset, category_id, *, using=None):
    """Apply category tree filter (M2M + primary FK). Returns queryset.none() if category missing."""
    if category_id in (None, "", 0):
        return queryset
    db = store_db_alias(getattr(queryset, "db", None) or using)
    try:
        category = Category.objects.using(db).get(pk=int(category_id), active=True)
    except (Category.DoesNotExist, TypeError, ValueError):
        return queryset.none()
    tree_ids = category_tree_ids(category, using=db)
    return queryset.filter(product_in_categories_q(tree_ids, using=db)).distinct()


def variant_keyword_q(keyword: str) -> Q:
    """Multi-field keyword match aligned with store search (products list API)."""
    q = (keyword or "").strip()
    if not q:
        return Q()
    return (
        Q(product__name__icontains=q)
        | Q(product__web_name__icontains=q)
        | Q(sku__icontains=q)
        | Q(product__mid__icontains=q)
        | Q(product__ingredients__icontains=q)
        | Q(packing__icontains=q)
    )


def count_variants_in_category_ids(category_ids, *, using=None) -> int:
    db = store_db_alias(using)
    return (
        ProductVariant.objects.using(db)
        .filter(active=True, is_published=True)
        .filter(product_in_categories_q(category_ids, using=db))
        .distinct()
        .count()
    )


def count_distinct_products_in_category_ids(category_ids, *, using=None) -> int:
    """Distinct active products in category tree (M2M + FK), for UI productCount."""
    db = store_db_alias(using)
    return (
        ProductVariant.objects.using(db)
        .filter(active=True, is_published=True, product__active=True)
        .filter(product_in_categories_q(category_ids, using=db))
        .values("product_id")
        .distinct()
        .count()
    )
