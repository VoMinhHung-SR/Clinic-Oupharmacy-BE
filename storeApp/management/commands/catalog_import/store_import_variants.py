"""Variant, unit, and batch upsert for catalog CSV/JSON import."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from django.utils import timezone

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import MedicineBatch, Product, ProductVariant, ProductVariantStats, ProductVariantUnit
from storeApp.services.stock import sync_in_stock_cache

from .store_import_packaging import (
    _normalize_unit_name,
    normalize_single_default_unit_per_variant,
    reconcile_single_default_variant_units_in_db,
)
from .store_import_row import (
    add_months,
    clip_db_str,
    compute_import_price_per_base_unit,
    compute_synthetic_batch_quantity,
    random_import_date,
    random_shelf_life,
    to_bool,
    to_int,
)


@dataclass
class VariantImportSettings:
    default_stock: int = 100
    batch_pack_mult_min: int = 10
    batch_pack_mult_max: int = 40
    batch_count: int = 1
    using: str = STORE_DATABASE_ALIAS


def build_variant_common(row: dict, images: list, settings: VariantImportSettings) -> dict:
    shelf_life = str(row.get("specifications.shelfLife") or "").strip()[:100] or random_shelf_life()
    return {
        "in_stock": settings.default_stock,
        "image": None,
        "images": images,
        "base_unit": "unit",
        "packing_meta": {
            "origin": str(row.get("specifications.origin") or "").strip()[:200],
            "manufacturer": str(row.get("specifications.manufacturer") or "").strip(),
            "shelf_life": shelf_life,
        },
        "product_ranking": to_int(row.get("metadata.productRanking"), 0),
        "is_published": to_bool(row.get("metadata.isPublish", "true"), True),
        "is_hot": to_bool(row.get("metadata.isHot", "false"), False),
    }


def count_simulated_batches(settings: VariantImportSettings) -> int:
    return settings.batch_count


def resolve_variant_sku(
    product: Product,
    row: dict,
    exclude_variant_id: Optional[int] = None,
    using: str = STORE_DATABASE_ALIAS,
) -> Optional[str]:
    mid = str(row.get("basicInfo.sku") or "").strip()[:100] or None
    if not mid:
        return None
    qs = ProductVariant.objects.using(using).filter(sku=mid)
    if exclude_variant_id:
        qs = qs.exclude(pk=exclude_variant_id)
    if qs.exists():
        return None
    return mid


def clear_variant_default_units(variant: ProductVariant, using: str = STORE_DATABASE_ALIAS) -> None:
    ProductVariantUnit.objects.using(using).filter(
        variant=variant,
        is_default=True,
    ).update(is_default=False)


def upsert_variant_units(
    variant: ProductVariant,
    units: list,
    *,
    is_published: bool,
    update_existing: bool,
    using: str = STORE_DATABASE_ALIAS,
) -> dict:
    normalize_single_default_unit_per_variant(units)
    stats = {"created": 0, "updated": 0}

    existing_units = {
        _normalize_unit_name(unit.unit_name): unit
        for unit in ProductVariantUnit.objects.using(using).filter(variant=variant)
    }

    for unit in units:
        unit_key = _normalize_unit_name(unit["unit_name"])
        unit_defaults = {
            "quantity_in_base": unit.get("quantity_in_base", 1),
            "unit_name": clip_db_str(unit.get("unit_name"), 50) or "Gói",
            "unit_order": unit.get("unit_order", 0),
            "price_value": unit.get("price_value") or 0,
            "price_display": clip_db_str(unit.get("price_display"), 50),
            "compare_at_price": None,
            "is_default": bool(unit.get("is_default")),
            "is_published": is_published,
        }
        existing_unit = existing_units.get(unit_key)
        if existing_unit:
            if update_existing:
                if unit_defaults["is_default"]:
                    clear_variant_default_units(variant, using=using)
                for field, val in unit_defaults.items():
                    setattr(existing_unit, field, val)
                existing_unit.save(using=using)
                stats["updated"] += 1
        else:
            if unit_defaults["is_default"]:
                clear_variant_default_units(variant, using=using)
            ProductVariantUnit.objects.using(using).create(
                variant=variant,
                **unit_defaults,
            )
            stats["created"] += 1

    reconcile_single_default_variant_units_in_db(variant, using=using)
    return stats


def upsert_variant_with_units(
    product: Product,
    payload: dict,
    variant_common: dict,
    row: dict,
    *,
    update_existing: bool,
    settings: VariantImportSettings,
) -> tuple[ProductVariant, bool, dict]:
    using = settings.using
    packing = payload["packing"]
    units = payload["units"]
    base_unit = payload["base_unit"]

    variant_fields = {
        **variant_common,
        "packing": packing,
        "base_unit": clip_db_str(base_unit, 50) or "Gói",
        "packing_meta": {
            **variant_common.get("packing_meta", {}),
            "units": [u["unit_name"] for u in units],
        },
    }

    existing_variant = (
        ProductVariant.objects.using(using)
        .filter(product=product, packing=packing)
        .first()
    )
    if not existing_variant and update_existing:
        siblings = list(
            ProductVariant.objects.using(using).filter(product=product).order_by("id")
        )
        if len(siblings) == 1:
            existing_variant = siblings[0]

    variant_fields["sku"] = resolve_variant_sku(
        product=product,
        row=row,
        exclude_variant_id=existing_variant.id if existing_variant else None,
        using=using,
    )

    if existing_variant:
        if update_existing:
            for field, val in variant_fields.items():
                setattr(existing_variant, field, val)
            existing_variant.save(using=using)
        variant_instance = existing_variant
        created = False
    else:
        variant_instance = ProductVariant.objects.using(using).create(
            product=product,
            **variant_fields,
        )
        created = True

    ProductVariantStats.objects.using(using).get_or_create(
        variant=variant_instance,
        defaults={
            "sold_total": 0,
            "sold_30d": 0,
            "sold_7d": 0,
            "view_count": 0,
            "wishlist_count": 0,
        },
    )
    unit_stats = upsert_variant_units(
        variant=variant_instance,
        units=units,
        is_published=to_bool(row.get("metadata.isPublish", "true"), True),
        update_existing=update_existing,
        using=using,
    )
    return variant_instance, created, unit_stats


def resolve_variant_default_unit(
    variant: ProductVariant,
    using: str = STORE_DATABASE_ALIAS,
) -> Optional[ProductVariantUnit]:
    unit = (
        ProductVariantUnit.objects.using(using)
        .filter(variant=variant, is_default=True)
        .order_by("unit_order", "id")
        .first()
    )
    if unit:
        return unit
    return (
        ProductVariantUnit.objects.using(using)
        .filter(variant=variant)
        .order_by("unit_order", "id")
        .first()
    )


def create_batches_for_variants(
    variants: list[ProductVariant],
    settings: VariantImportSettings,
) -> int:
    using = settings.using
    today = timezone.now().date()
    created = 0
    used_numbers: set = set(
        MedicineBatch.objects.using(using).values_list("batch_number", flat=True)
    )

    for variant in variants:
        MedicineBatch.objects.using(using).filter(product_variant=variant).delete()

        default_unit = resolve_variant_default_unit(variant, using=using)
        qib = max(default_unit.quantity_in_base, 1) if default_unit else 1
        import_price_per_base = None
        if default_unit and default_unit.price_value:
            import_price_per_base = compute_import_price_per_base_unit(
                default_unit.price_value,
                qib,
            )

        for _ in range(settings.batch_count):
            import_date = random_import_date(today)
            expiry_months = random.choice([6, 12, 18, 24, 36])
            expiry_date = add_months(import_date, expiry_months)
            quantity = compute_synthetic_batch_quantity(
                qib,
                settings.batch_pack_mult_min,
                settings.batch_pack_mult_max,
            )

            for _ in range(50):
                suffix = random.randint(1000, 9999)
                batch_num = f"BATCH{import_date.strftime('%Y%m%d')}{variant.id}{suffix}"
                if batch_num not in used_numbers:
                    used_numbers.add(batch_num)
                    break
            else:
                batch_num = f"BATCH{import_date.strftime('%Y%m%d')}{variant.id}{random.randint(10000, 99999)}"
                used_numbers.add(batch_num)

            MedicineBatch.objects.using(using).create(
                batch_number=batch_num,
                product_variant=variant,
                import_date=import_date,
                expiry_date=expiry_date,
                quantity=quantity,
                remaining_quantity=quantity,
                import_price_per_base_unit=import_price_per_base,
                active=True,
            )
            created += 1

        sync_in_stock_cache(variant.id)

    return created
