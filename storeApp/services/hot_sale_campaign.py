"""
Hot-sale campaign: popular products + real catalog tier promos (P1 / D-PRC Option 1).

Lowers price_value and sets compare_at_price to list reference; snapshots revert data
on ProductUnitPromotion.

Plan: PersonalProject/plans/[UnDone] catalog-pricing-direct-discount-refactor.plan.md
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db.models import F, Prefetch

from storeApp.management.commands.catalog_import.store_import_pricing import PRICE_DISPLAY_CONSULT
from storeApp.models import (
    Campaign,
    CampaignProduct,
    CampaignVoucher,
    ProductUnitPromotion,
    ProductVariant,
    ProductVariantUnit,
    Voucher,
)
from storeApp.services.campaign_cache import invalidate_public_campaign_cache
from storeApp.services.product_pricing import TierPromoPrices, tier_promo_prices
from storeApp.services.product_promotion import (
    apply_unit_promotion,
    revert_campaign_promotions_by_slug,
)
from storeApp.services.variant_listing import one_variant_per_product
from storeApp.viewsets.product import annotate_variant_unit_price

HOT_SALE_CAMPAIGN_SLUG = "san-pham-ban-chay"
HOT_SALE_TIERS = (30, 25, 20)
HOT_SALE_PAGE_SIZE = 12
HOT_SALE_FETCH_SIZE = 48
HOT_SALE_VOUCHER_CODES = ("SALE30", "SALE25", "SALE20")


@dataclass(frozen=True)
class HotSalePlanRow:
    variant: ProductVariant
    unit: ProductVariantUnit
    product_mid: str
    tier_percent: int
    promo: TierPromoPrices


def tier_percent_for_index(index: int) -> int:
    return HOT_SALE_TIERS[index % len(HOT_SALE_TIERS)]


def is_priced_for_hot_sale(unit: ProductVariantUnit | None, price_value: Decimal) -> bool:
    if unit is not None and str(unit.price_display or "").strip().upper() == PRICE_DISPLAY_CONSULT:
        return False
    return price_value > 0


def get_default_unit(variant: ProductVariant) -> ProductVariantUnit | None:
    units = getattr(variant, "prefetched_units", None)
    if units is None:
        units = list(variant.units.filter(is_published=True).order_by("unit_order", "id"))
    for unit in units:
        if unit.is_default:
            return unit
    return units[0] if units else None


def iter_published_priced_units(variant: ProductVariant) -> list[ProductVariantUnit]:
    """All published sale units on a variant (hot-sale applies per unit, same tier %)."""
    units = getattr(variant, "prefetched_units", None)
    if units is None:
        units = list(variant.units.filter(is_published=True).order_by("unit_order", "id"))
    return [u for u in units if is_priced_for_hot_sale(u, u.price_value)]


def apply_hot_sale_tier_to_variant(
    campaign: Campaign,
    variant: ProductVariant,
    tier_percent: int,
    *,
    starts_at=None,
    ends_at=None,
    dry_run: bool = False,
    using: str = "store",
) -> int:
    """
    Apply one tier % to every published priced unit on the variant (D-PRC / multi-unitsale).
    Default unit drives hot-sale ranking; sibling units (Chai/Thùng) get proportional list/sale.
    """
    applied = 0
    for unit in iter_published_priced_units(variant):
        promo = tier_promo_prices(unit, tier_percent)
        if promo is None:
            continue
        apply_unit_promotion(
            campaign=campaign,
            unit=unit,
            promo=promo,
            tier_percent=tier_percent,
            source=ProductUnitPromotion.SOURCE_HOT_SALE,
            starts_at=starts_at,
            ends_at=ends_at,
            dry_run=dry_run,
            using=using,
        )
        applied += 1
    return applied


def fetch_popular_variants_for_hot_sale(
    using: str,
    *,
    fetch_size: int = HOT_SALE_FETCH_SIZE,
) -> list[ProductVariant]:
    unit_qs = (
        ProductVariantUnit.objects.using(using)
        .filter(is_published=True)
        .order_by("unit_order", "id")
    )
    qs = annotate_variant_unit_price(
        ProductVariant.objects.using(using)
        .filter(active=True, is_published=True, product__active=True)
        .select_related("product")
        .prefetch_related(Prefetch("units", queryset=unit_qs, to_attr="prefetched_units")),
        db_alias=using,
    ).filter(price_value__gt=0)

    deduped = one_variant_per_product(
        qs,
        partition_order=[
            F("product_id").asc(),
            F("product_ranking").desc(),
            F("id").asc(),
        ],
    )
    return list(deduped.order_by("-product_ranking", "-in_stock", "id")[:fetch_size])


def plan_hot_sale_rows(
    variants: Iterable[ProductVariant],
    *,
    page_size: int = HOT_SALE_PAGE_SIZE,
) -> list[HotSalePlanRow]:
    rows: list[HotSalePlanRow] = []
    index = 0
    for variant in variants:
        unit = get_default_unit(variant)
        price = variant.price_value
        if unit is None or not is_priced_for_hot_sale(unit, price):
            continue
        mid = (variant.product.mid or "").strip()
        if not mid:
            continue

        tier = tier_percent_for_index(index)
        promo = tier_promo_prices(unit, tier)
        if promo is None:
            continue

        rows.append(
            HotSalePlanRow(
                variant=variant,
                unit=unit,
                product_mid=mid,
                tier_percent=tier,
                promo=promo,
            )
        )
        index += 1
        if index >= page_size:
            break

    rows.sort(key=lambda row: (-row.promo.discount_percent, row.variant.product.name.casefold()))
    return rows


def apply_hot_sale_plan_row(
    campaign: Campaign,
    row: HotSalePlanRow,
    *,
    starts_at=None,
    ends_at=None,
    dry_run: bool = False,
    using: str = "store",
) -> ProductVariantUnit:
    return apply_unit_promotion(
        campaign=campaign,
        unit=row.unit,
        promo=row.promo,
        tier_percent=row.tier_percent,
        source=ProductUnitPromotion.SOURCE_HOT_SALE,
        starts_at=starts_at,
        ends_at=ends_at,
        dry_run=dry_run,
        using=using,
    )


def upsert_hot_sale_campaign(
    plans: list[HotSalePlanRow],
    *,
    using: str = "store",
    dry_run: bool = False,
    start_at=None,
    end_at=None,
    priority: int = 150,
) -> Campaign | None:
    if dry_run:
        return None

    campaign, _created = Campaign.objects.using(using).update_or_create(
        slug=HOT_SALE_CAMPAIGN_SLUG,
        defaults={
            "name": "Sản phẩm bán chạy",
            "title": "Sản phẩm bán chạy",
            "subtitle": "Giảm giá catalog theo tier 30% / 25% / 20% (giá sale thật)",
            "description_html": (
                "<p>Chiến dịch áp promotion catalog: hạ <code>price_value</code>, "
                "<code>compare_at_price</code> = giá niêm yết. Revert qua "
                "<code>seed_hot_sale_campaign --revert-promo</code>.</p>"
            ),
            "status": Campaign.STATUS_ACTIVE,
            "priority": priority,
            "start_at": start_at,
            "end_at": end_at,
            "locale": "vi",
        },
    )

    for plan in plans:
        apply_hot_sale_tier_to_variant(
            campaign,
            plan.variant,
            plan.tier_percent,
            starts_at=start_at,
            ends_at=end_at,
            using=using,
        )

    CampaignProduct.objects.using(using).filter(campaign=campaign).delete()
    for sort_order, plan in enumerate(plans):
        CampaignProduct.objects.using(using).create(
            campaign=campaign,
            product_mid=plan.product_mid,
            sort_order=sort_order,
        )

    for sort_order, code in enumerate(HOT_SALE_VOUCHER_CODES):
        voucher = Voucher.objects.using(using).filter(code=code).first()
        if voucher is None:
            continue
        CampaignVoucher.objects.using(using).update_or_create(
            campaign=campaign,
            voucher=voucher,
            defaults={"sort_order": sort_order, "is_featured": True},
        )

    invalidate_public_campaign_cache()
    return campaign


def revert_hot_sale_promotions(
    *,
    using: str = "store",
    dry_run: bool = False,
) -> int:
    return revert_campaign_promotions_by_slug(
        HOT_SALE_CAMPAIGN_SLUG,
        using=using,
        dry_run=dry_run,
    )


def revert_hot_sale_compare_at(
    *,
    using: str = "store",
    dry_run: bool = False,
) -> int:
    """Backward-compatible alias — full promo revert (price + compare_at)."""
    return revert_hot_sale_promotions(using=using, dry_run=dry_run)
