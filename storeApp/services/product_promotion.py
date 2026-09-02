"""
Unified catalog unit promotion lifecycle (P1b / D-PRC).

Any program that lowers ProductVariantUnit.price_value must snapshot ProductUnitPromotion
and rely on revert_expired_unit_promotions (hooked from run_campaign_scheduler).
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from storeApp.models import Campaign, ProductUnitPromotion, ProductVariantUnit
from storeApp.services.product_pricing import TierPromoPrices


def promo_is_expired(promo: ProductUnitPromotion, *, now, campaign: Campaign | None = None) -> bool:
    """True when promo window or linked campaign window has ended."""
    if promo.ends_at is not None and now >= promo.ends_at:
        return True
    camp = campaign if campaign is not None else promo.campaign
    if camp.status == Campaign.STATUS_ENDED:
        return True
    if camp.end_at is not None and now >= camp.end_at:
        return True
    return False


def _active_promos_for_unit(
    unit_id: int,
    *,
    using: str,
    exclude_promo_id: int | None = None,
):
    qs = (
        ProductUnitPromotion.objects.using(using)
        .filter(product_variant_unit_id=unit_id, is_active=True)
        .select_related("campaign")
    )
    if exclude_promo_id is not None:
        qs = qs.exclude(pk=exclude_promo_id)
    return list(qs.order_by("-campaign__priority", "-id"))


def _apply_promo_prices_to_unit(unit: ProductVariantUnit, promo: ProductUnitPromotion, *, using: str) -> None:
    unit.price_value = promo.sale_price
    unit.compare_at_price = promo.list_price
    unit.save(using=using, update_fields=["price_value", "compare_at_price"])


def _sync_unit_price_from_remaining_promos(
    unit_id: int,
    *,
    using: str,
    fallback_previous_price: Decimal,
    fallback_previous_compare: Decimal | None,
) -> None:
    remaining = _active_promos_for_unit(unit_id, using=using)
    unit = ProductVariantUnit.objects.using(using).get(pk=unit_id)
    if remaining:
        _apply_promo_prices_to_unit(unit, remaining[0], using=using)
        return
    unit.price_value = fallback_previous_price
    unit.compare_at_price = fallback_previous_compare
    unit.save(using=using, update_fields=["price_value", "compare_at_price"])


def apply_unit_promotion(
    *,
    campaign: Campaign,
    unit: ProductVariantUnit,
    promo: TierPromoPrices,
    tier_percent: int,
    source: str = ProductUnitPromotion.SOURCE_HOT_SALE,
    starts_at=None,
    ends_at=None,
    dry_run: bool = False,
    using: str = "store",
) -> ProductVariantUnit:
    """Lower unit catalog price and upsert ProductUnitPromotion snapshot."""
    previous_price = unit.price_value
    previous_compare = unit.compare_at_price

    if not dry_run:
        unit.compare_at_price = promo.list_price
        unit.price_value = promo.sale_price
        unit.save(using=using, update_fields=["compare_at_price", "price_value"])

        ProductUnitPromotion.objects.using(using).update_or_create(
            campaign=campaign,
            product_variant_unit_id=unit.id,
            defaults={
                "source": source,
                "tier_percent": tier_percent,
                "list_price": promo.list_price,
                "sale_price": promo.sale_price,
                "previous_price_value": previous_price,
                "previous_compare_at_price": previous_compare,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "is_active": True,
            },
        )
        unit.refresh_from_db(using=using)

    return unit


def revert_unit_promotion(
    promo: ProductUnitPromotion,
    *,
    using: str = "store",
    dry_run: bool = False,
) -> bool:
    """
    Deactivate one promo and restore unit price.

    When other active promos remain on the unit, keep the highest-priority winner's sale/list.
    """
    if not promo.is_active:
        return False

    unit = promo.product_variant_unit
    if unit is None:
        if not dry_run:
            promo.is_active = False
            promo.save(using=using, update_fields=["is_active"])
        return True

    if not dry_run:
        promo.is_active = False
        promo.save(using=using, update_fields=["is_active"])
        _sync_unit_price_from_remaining_promos(
            unit.id,
            using=using,
            fallback_previous_price=promo.previous_price_value,
            fallback_previous_compare=promo.previous_compare_at_price,
        )

    return True


def revert_campaign_promotions(
    campaign: Campaign,
    *,
    using: str = "store",
    dry_run: bool = False,
) -> int:
    """Revert all active unit promos for one campaign."""
    promos = list(
        ProductUnitPromotion.objects.using(using)
        .filter(campaign=campaign, is_active=True)
        .select_related("product_variant_unit", "campaign")
    )
    reverted = 0
    for promo in promos:
        if revert_unit_promotion(promo, using=using, dry_run=dry_run):
            reverted += 1
    return reverted


def revert_campaign_promotions_by_slug(
    slug: str,
    *,
    using: str = "store",
    dry_run: bool = False,
) -> int:
    campaign = Campaign.objects.using(using).filter(slug=slug).first()
    if campaign is None:
        return 0
    return revert_campaign_promotions(campaign, using=using, dry_run=dry_run)


def _expired_promo_query(now):
    return Q(is_active=True) & (
        Q(ends_at__isnull=False, ends_at__lte=now)
        | Q(campaign__status=Campaign.STATUS_ENDED)
        | Q(campaign__end_at__isnull=False, campaign__end_at__lte=now)
    )


def revert_expired_unit_promotions(
    *,
    now=None,
    using: str = "store",
    dry_run: bool = False,
) -> dict:
    """
    Revert all expired active promos (any source). Idempotent.
    Returns stats: scanned, reverted.
    """
    now = now or timezone.now()
    promos = list(
        ProductUnitPromotion.objects.using(using)
        .filter(_expired_promo_query(now))
        .select_related("product_variant_unit", "campaign")
        .order_by("campaign_id", "id")
    )
    reverted = 0
    for promo in promos:
        if revert_unit_promotion(promo, using=using, dry_run=dry_run):
            reverted += 1
    return {"scanned": len(promos), "reverted": reverted}
