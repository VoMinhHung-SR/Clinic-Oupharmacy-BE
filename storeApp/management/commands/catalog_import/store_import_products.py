"""Product + brand upsert for catalog CSV/JSON import."""

from __future__ import annotations

from typing import Optional

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import Brand, Category, Product

from .store_import_row import extract_country_from_row, normalize_brand, row_text


def resolve_brand(
    row: dict,
    brand_cache: dict,
    *,
    dry_run: bool,
    using: str = STORE_DATABASE_ALIAS,
) -> tuple[Optional[int], int]:
    """
    Returns (brand_id or None, brands_created count).
    dry_run: increments counter but does not persist.
    """
    stats_created = 0
    raw_name = str(row.get("basicInfo.brand") or "").strip()
    brand_name = normalize_brand(raw_name)
    if not brand_name:
        return None, 0

    if brand_name in brand_cache:
        brand_id = brand_cache[brand_name]
        if brand_id and brand_id > 0:
            if not dry_run and not Brand.objects.using(using).filter(pk=brand_id).exists():
                # Stale cache after a rolled-back row (brand created then txn failed).
                del brand_cache[brand_name]
            elif not dry_run:
                country = extract_country_from_row(row)
                if country:
                    Brand.objects.using(using).filter(id=brand_id, country__isnull=True).update(country=country)
                    Brand.objects.using(using).filter(id=brand_id).exclude(country=country).update(country=country)
                return brand_id, 0
            elif dry_run:
                return None, 0
        elif brand_id == -1 and dry_run:
            return None, 0
        elif brand_id == -1:
            del brand_cache[brand_name]

    if dry_run:
        brand_cache[brand_name] = -1
        return None, 1

    country = extract_country_from_row(row)
    brand, created = Brand.objects.using(using).get_or_create(
        name=brand_name,
        defaults={"country": country, "active": True},
    )
    if created:
        stats_created = 1
    elif country and brand.country != country:
        brand.country = country
        brand.save(update_fields=["country"], using=using)

    brand_cache[brand_name] = brand.id
    return brand.id, stats_created


def build_product_defaults(row: dict, brand_id: Optional[int]) -> dict:
    name = str(row.get("basicInfo.name") or "").strip()
    sku_raw = row.get("basicInfo.sku")
    mid = str(sku_raw).strip() if sku_raw not in (None, "") else None
    slug = str(row.get("basicInfo.slug") or "").strip() or None

    return {
        "name": name,
        "mid": mid,
        "slug": slug,
        "web_name": row_text(row, "basicInfo.webName"),
        "description": row_text(row, "content.description"),
        "ingredients": row_text(row, "content.ingredients"),
        "usage": row_text(row, "content.usage"),
        "dosage": row_text(row, "content.dosage"),
        "adverse_effect": row_text(row, "content.adverseEffect"),
        "careful": row_text(row, "content.careful"),
        "preservation": row_text(row, "content.preservation"),
        "brand_id": brand_id,
    }


def upsert_product_from_row(
    row: dict,
    brand_id: Optional[int],
    leaf_category: Optional[Category],
    *,
    update_existing: bool,
    dry_run: bool,
    using: str = STORE_DATABASE_ALIAS,
) -> tuple[Optional[Product], dict]:
    """
    Upsert Product by mid → slug → name; merge category via ProductCategory M2M.

    Returns (product or None on dry-run/missing name, stats dict).
    """
    stats = {
        "products_created": 0,
        "products_updated": 0,
        "product_categories_linked": 0,
    }
    defaults = build_product_defaults(row, brand_id)
    if not defaults["name"]:
        return None, stats

    if dry_run:
        stats["products_created"] = 1
        if leaf_category:
            stats["product_categories_linked"] = 1
        return None, stats

    product = None
    mid, slug = defaults["mid"], defaults["slug"]
    if mid:
        product = Product.objects.using(using).filter(mid=mid).first()
    if not product and slug:
        product = Product.objects.using(using).filter(slug=slug).first()
    if not product:
        product = Product.objects.using(using).filter(name=defaults["name"]).first()

    write_defaults = {k: v for k, v in defaults.items() if k != "name" or product is None}

    if product:
        if update_existing:
            update_fields = []
            for field, val in write_defaults.items():
                attr = field
                if getattr(product, attr, None) != val:
                    setattr(product, field, val)
                    update_fields.append(field)
            if update_fields:
                product.save(using=using, update_fields=update_fields)
                stats["products_updated"] = 1
    else:
        product = Product.objects.using(using).create(**defaults)
        stats["products_created"] = 1

    if leaf_category:
        link = product.assign_category(leaf_category, using=using, set_primary_if_none=True)
        if link:
            stats["product_categories_linked"] = 1

    return product, stats
