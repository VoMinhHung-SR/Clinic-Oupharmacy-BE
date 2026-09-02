"""
P4 rollout audit + cleanup helpers for catalog pricing (D-PRC).

Detect legacy compare_at-only merch (pre-P1 hot-sale seed) and report rollout readiness.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Exists, F, OuterRef

from storeApp.models import CartItem, ProductUnitPromotion, ProductVariantUnit
from storeApp.services.hot_sale_campaign import HOT_SALE_TIERS
from storeApp.services.product_pricing import discount_percent_from_prices, sale_price_from_list

HOT_SALE_TIER_SET = set(HOT_SALE_TIERS)


@dataclass(frozen=True)
class LegacyCompareAtRow:
    unit_id: int
    price_value: Decimal
    compare_at_price: Decimal
    discount_percent: int
    tier_match: int | None


@dataclass(frozen=True)
class CatalogPricingAuditReport:
    units_with_display_discount: int
    units_with_active_promo: int
    legacy_compare_only_count: int
    legacy_rows: list[LegacyCompareAtRow]
    cart_items_missing_list_snapshot: int
    cart_items_with_null_list_but_compare: int


def _reverse_tier_match(*, price: Decimal, compare: Decimal) -> int | None:
    """True when compare looks like price / (1 − tier%) — old P0 merch-only seed."""
    for tier in HOT_SALE_TIERS:
        implied_compare = price / (Decimal(1) - (Decimal(tier) / Decimal(100)))
        if abs(implied_compare - compare) <= Decimal("2"):
            return tier
    return None


def is_legacy_reverse_compare_at(
    *,
    price_value: Decimal,
    compare_at_price: Decimal,
    product_mid: str | None = None,
    hot_sale_mids: set[str] | None = None,
) -> bool:
    """
    Heuristic: compare_at was reverse-computed from unchanged price_value (P0 debt).

    Requires hot-sale tier match AND (when hot_sale_mids provided) product on hot-sale campaign.
    """
    price = Decimal(price_value)
    compare = Decimal(compare_at_price)
    if compare <= price:
        return False
    tier = _reverse_tier_match(price=price, compare=compare)
    if tier is None:
        return False
    pct = discount_percent_from_prices(price, compare)
    if pct not in HOT_SALE_TIER_SET:
        return False
    if hot_sale_mids is not None:
        mid = (product_mid or "").strip()
        if not mid or mid not in hot_sale_mids:
            return False
    return True


def _hot_sale_product_mids(*, using: str = "store") -> set[str]:
    from storeApp.models import Campaign, CampaignProduct
    from storeApp.services.hot_sale_campaign import HOT_SALE_CAMPAIGN_SLUG

    campaign = Campaign.objects.using(using).filter(slug=HOT_SALE_CAMPAIGN_SLUG).first()
    if campaign is None:
        return set()
    return set(
        CampaignProduct.objects.using(using)
        .filter(campaign=campaign)
        .values_list("product_mid", flat=True)
    )


def find_legacy_compare_only_units(*, using: str = "store", limit: int = 50) -> list[LegacyCompareAtRow]:
    hot_sale_mids = _hot_sale_product_mids(using=using)
    active_promo = ProductUnitPromotion.objects.using(using).filter(
        product_variant_unit_id=OuterRef("pk"),
        is_active=True,
    )
    qs = (
        ProductVariantUnit.objects.using(using)
        .filter(compare_at_price__isnull=False, price_value__gt=0)
        .select_related("variant__product")
        .annotate(has_active_promo=Exists(active_promo))
        .filter(has_active_promo=False)
        .filter(compare_at_price__gt=F("price_value"))
    )
    rows: list[LegacyCompareAtRow] = []
    for unit in qs[: limit * 3]:
        price = Decimal(unit.price_value)
        compare = Decimal(unit.compare_at_price)
        mid = (unit.variant.product.mid or "") if unit.variant and unit.variant.product else ""
        if not is_legacy_reverse_compare_at(
            price_value=price,
            compare_at_price=compare,
            product_mid=mid,
            hot_sale_mids=hot_sale_mids if hot_sale_mids else None,
        ):
            continue
        rows.append(
            LegacyCompareAtRow(
                unit_id=unit.id,
                price_value=price,
                compare_at_price=compare,
                discount_percent=discount_percent_from_prices(price, compare),
                tier_match=_reverse_tier_match(price=price, compare=compare),
            )
        )
        if len(rows) >= limit:
            break
    return rows


def count_legacy_compare_only_units(*, using: str = "store") -> int:
    hot_sale_mids = _hot_sale_product_mids(using=using)
    active_promo = ProductUnitPromotion.objects.using(using).filter(
        product_variant_unit_id=OuterRef("pk"),
        is_active=True,
    )
    qs = (
        ProductVariantUnit.objects.using(using)
        .filter(compare_at_price__isnull=False, price_value__gt=0)
        .select_related("variant__product")
        .annotate(has_active_promo=Exists(active_promo))
        .filter(has_active_promo=False)
        .filter(compare_at_price__gt=F("price_value"))
    )
    count = 0
    for unit in qs.iterator():
        mid = (unit.variant.product.mid or "") if unit.variant and unit.variant.product else ""
        if is_legacy_reverse_compare_at(
            price_value=Decimal(unit.price_value),
            compare_at_price=Decimal(unit.compare_at_price),
            product_mid=mid,
            hot_sale_mids=hot_sale_mids if hot_sale_mids else None,
        ):
            count += 1
    return count


def audit_catalog_pricing(*, using: str = "store", legacy_sample: int = 20) -> CatalogPricingAuditReport:
    active_promo = ProductUnitPromotion.objects.using(using).filter(
        product_variant_unit_id=OuterRef("pk"),
        is_active=True,
    )
    units_with_display = (
        ProductVariantUnit.objects.using(using)
        .filter(compare_at_price__isnull=False, price_value__gt=0)
        .filter(compare_at_price__gt=F("price_value"))
        .count()
    )
    units_with_promo = (
        ProductUnitPromotion.objects.using(using)
        .filter(is_active=True)
        .values("product_variant_unit_id")
        .distinct()
        .count()
    )
    legacy_rows = find_legacy_compare_only_units(using=using, limit=legacy_sample)
    legacy_count = count_legacy_compare_only_units(using=using)
    missing_list = CartItem.objects.using(using).filter(list_price_snapshot__isnull=True).count()
    missing_but_compare = (
        CartItem.objects.using(using)
        .filter(list_price_snapshot__isnull=True, product_variant_unit__compare_at_price__isnull=False)
        .filter(product_variant_unit__compare_at_price__gt=F("unit_price_snapshot"))
        .count()
    )
    return CatalogPricingAuditReport(
        units_with_display_discount=units_with_display,
        units_with_active_promo=units_with_promo,
        legacy_compare_only_count=legacy_count,
        legacy_rows=legacy_rows,
        cart_items_missing_list_snapshot=missing_list,
        cart_items_with_null_list_but_compare=missing_but_compare,
    )


def clear_legacy_reverse_compare_at(*, using: str = "store", dry_run: bool = False) -> int:
    """Null compare_at on hot-sale-scoped P0 reverse merch units without active promo."""
    hot_sale_mids = _hot_sale_product_mids(using=using)
    active_promo = ProductUnitPromotion.objects.using(using).filter(
        product_variant_unit_id=OuterRef("pk"),
        is_active=True,
    )
    candidates = (
        ProductVariantUnit.objects.using(using)
        .filter(compare_at_price__isnull=False, price_value__gt=0)
        .select_related("variant__product")
        .annotate(has_active_promo=Exists(active_promo))
        .filter(has_active_promo=False)
        .filter(compare_at_price__gt=F("price_value"))
    )
    cleared = 0
    for unit in candidates.iterator():
        price = Decimal(unit.price_value)
        compare = Decimal(unit.compare_at_price)
        mid = (unit.variant.product.mid or "") if unit.variant and unit.variant.product else ""
        if not is_legacy_reverse_compare_at(
            price_value=price,
            compare_at_price=compare,
            product_mid=mid,
            hot_sale_mids=hot_sale_mids if hot_sale_mids else None,
        ):
            continue
        if not dry_run:
            unit.compare_at_price = None
            unit.save(using=using, update_fields=["compare_at_price"])
        cleared += 1
    return cleared


def backfill_cart_list_price_snapshots(*, using: str = "store", dry_run: bool = False) -> int:
    """Set list_price_snapshot on cart lines added before P2 migration."""
    from storeApp.services.product_pricing import list_price_snapshot_from_unit

    updated = 0
    qs = CartItem.objects.using(using).filter(list_price_snapshot__isnull=True).select_related(
        "product_variant_unit"
    )
    for item in qs.iterator():
        unit = item.product_variant_unit
        if unit is None:
            continue
        sale = Decimal(item.unit_price_snapshot or unit.price_value or 0)
        list_snap = list_price_snapshot_from_unit(unit, sale)
        if list_snap is None:
            continue
        if not dry_run:
            item.list_price_snapshot = list_snap
            item.save(using=using, update_fields=["list_price_snapshot"])
        updated += 1
    return updated


def verify_p1_promo_integrity(*, using: str = "store", sample_limit: int = 100) -> list[str]:
    """
    Spot-check active promos: sale/list on unit should match promo row.
    Returns human-readable issues (empty = OK).
    """
    issues: list[str] = []
    promos = (
        ProductUnitPromotion.objects.using(using)
        .filter(is_active=True)
        .select_related("product_variant_unit")[:sample_limit]
    )
    for promo in promos:
        unit = promo.product_variant_unit
        if unit is None:
            issues.append(f"promo {promo.id}: missing unit")
            continue
        if Decimal(unit.price_value) != Decimal(promo.sale_price):
            issues.append(
                f"unit {unit.id}: price_value {unit.price_value} != promo.sale_price {promo.sale_price}"
            )
        if unit.compare_at_price is not None and Decimal(unit.compare_at_price) != Decimal(promo.list_price):
            issues.append(
                f"unit {unit.id}: compare_at {unit.compare_at_price} != promo.list_price {promo.list_price}"
            )
        expected_sale = sale_price_from_list(Decimal(promo.list_price), promo.tier_percent)
        if expected_sale is not None and abs(expected_sale - Decimal(promo.sale_price)) > Decimal("2"):
            issues.append(f"promo {promo.id}: tier math mismatch list/sale/tier")
    return issues
