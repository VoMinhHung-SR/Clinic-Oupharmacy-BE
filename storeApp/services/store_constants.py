"""
Store-wide business constants (checkout, promotions).
Override via Django settings when needed (e.g. staging).
"""
from decimal import Decimal

from django.conf import settings

FREE_SHIPPING_ORDER_SUBTOTAL = Decimal(
    str(getattr(settings, "FREE_SHIPPING_ORDER_SUBTOTAL", 300_000))
)


def qualifies_for_free_shipping(order_subtotal: Decimal) -> bool:
    """True when line subtotal (checkout scope) meets the free-shipping threshold."""
    return order_subtotal >= FREE_SHIPPING_ORDER_SUBTOTAL


def apply_free_shipping_base(order_subtotal: Decimal, shipping_fee_base: Decimal) -> Decimal:
    """
    Return shipping fee base after order-level free-shipping promotion.
    Applied before shipping vouchers (base passed to resolve_voucher_discounts).
    """
    if qualifies_for_free_shipping(order_subtotal):
        return Decimal("0")
    return shipping_fee_base
