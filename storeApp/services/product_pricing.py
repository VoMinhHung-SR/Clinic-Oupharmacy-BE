"""
Catalog unit pricing helpers (D-PRC Option 1).

Sale promotions lower price_value and set compare_at_price to the list reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class UnitPriceDisplay:
    price_value: Decimal
    compare_at_price: Decimal | None
    discount_percent: int


@dataclass(frozen=True)
class TierPromoPrices:
    list_price: Decimal
    sale_price: Decimal
    discount_percent: int


def discount_percent_from_prices(price_value: Decimal | None, compare_at_price: Decimal | None) -> int:
    if price_value is None or compare_at_price is None:
        return 0
    price = Decimal(price_value)
    compare = Decimal(compare_at_price)
    if compare <= price or compare <= 0 or price <= 0:
        return 0
    return int(round((compare - price) / compare * 100))


def resolve_unit_prices(unit) -> UnitPriceDisplay:
    """Read current catalog prices on a ProductVariantUnit."""
    price = Decimal(unit.price_value or 0)
    compare_raw = unit.compare_at_price
    compare = Decimal(compare_raw) if compare_raw is not None else None
    if compare is not None and compare <= price:
        compare = None
    return UnitPriceDisplay(
        price_value=price,
        compare_at_price=compare,
        discount_percent=discount_percent_from_prices(price, compare),
    )


def list_price_for_promotion(unit) -> Decimal:
    """
    List / reference price before applying a tier promo.
    Prefer existing compare_at when it is above current sale price.
    """
    price = Decimal(unit.price_value or 0)
    compare = unit.compare_at_price
    if compare is not None:
        compare_dec = Decimal(compare)
        if compare_dec > price:
            return compare_dec
    return price


def sale_price_from_list(list_price: Decimal, tier_percent: int) -> Decimal | None:
    """Compute sale price from list reference and tier % (lowers price — D-PRC-04)."""
    if tier_percent <= 0 or list_price <= 0:
        return None
    factor = Decimal(1) - (Decimal(tier_percent) / Decimal(100))
    if factor <= 0:
        return None
    raw = list_price * factor
    sale = raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if sale <= 0:
        return None
    if sale >= list_price:
        return max(Decimal("1"), list_price - Decimal("1"))
    return sale


def tier_promo_prices(unit, tier_percent: int) -> TierPromoPrices | None:
    list_price = list_price_for_promotion(unit)
    sale_price = sale_price_from_list(list_price, tier_percent)
    if sale_price is None:
        return None
    return TierPromoPrices(
        list_price=list_price,
        sale_price=sale_price,
        discount_percent=discount_percent_from_prices(sale_price, list_price),
    )
