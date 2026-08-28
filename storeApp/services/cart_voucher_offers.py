"""Eligible cart voucher offers for merchandising UI (list + best pick)."""

from decimal import Decimal

from django.utils import timezone

from storeApp.models import Voucher
from storeApp.services.cart_service import _build_context
from storeApp.services.voucher_engine import _get_redeem_count_map


def _serialize_offer(*, voucher, estimated_discount, applied_code):
    return {
        "code": voucher.code,
        "description": voucher.description,
        "type": voucher.type,
        "value": str(voucher.value),
        "scope": voucher.scope,
        "estimated_discount": str(estimated_discount.quantize(Decimal("0.01"))),
        "end_at": voucher.end_at.isoformat() if voucher.end_at else None,
        "is_applied": bool(applied_code and voucher.code == applied_code),
    }


def _collect_scope_offers(
    *,
    scope,
    vouchers,
    redeem_count_map,
    subtotal,
    shipping_fee_base,
    product_mids,
    category_slugs,
    user_id,
    applied_code,
    using,
):
    offers = []

    for voucher in vouchers:
        if voucher.scope != scope:
            continue
        if not voucher.is_valid():
            continue
        is_valid, _ = voucher.validate_for_context(
            order_subtotal=subtotal,
            product_mids=product_mids,
            category_slugs=category_slugs,
            user_id=user_id,
            current_user_redeem_count=redeem_count_map.get(voucher.id, 0),
            using=using,
        )
        if not is_valid:
            continue
        estimated_discount = voucher.calculate_discount_for_scope(
            order_subtotal=subtotal,
            shipping_fee=shipping_fee_base,
        )
        if scope == Voucher.SHIPPING_DISCOUNT:
            estimated_discount = min(estimated_discount, shipping_fee_base)
        if estimated_discount <= Decimal("0"):
            continue
        offers.append(
            _serialize_offer(
                voucher=voucher,
                estimated_discount=estimated_discount,
                applied_code=applied_code,
            )
        )

    offers.sort(key=lambda row: Decimal(row["estimated_discount"]), reverse=True)
    return offers


def list_cart_voucher_offers(*, cart, user_id=None, using="store", item_ids=None):
    """
    Return displayable eligible vouchers for the active cart context.

    item_ids mirrors checkout subset selection when provided.
    """
    _, subtotal, shipping_fee_base, product_mids, category_slugs, _ = _build_context(
        cart=cart,
        using=using,
        item_ids=item_ids,
    )
    applied_order_code = cart.order_voucher.code if cart.order_voucher else None
    applied_shipping_code = cart.shipping_voucher.code if cart.shipping_voucher else None
    resolved_user_id = user_id or cart.user_id

    vouchers = list(
        Voucher.objects.using(using)
        .filter(
            is_active=True,
            scope__in=[Voucher.ORDER_DISCOUNT, Voucher.SHIPPING_DISCOUNT],
        )
        .order_by("-value", "code")
    )
    redeem_count_map = _get_redeem_count_map(resolved_user_id, vouchers, using)

    order_vouchers = _collect_scope_offers(
        scope=Voucher.ORDER_DISCOUNT,
        vouchers=vouchers,
        redeem_count_map=redeem_count_map,
        subtotal=subtotal,
        shipping_fee_base=shipping_fee_base,
        product_mids=product_mids,
        category_slugs=category_slugs,
        user_id=resolved_user_id,
        applied_code=applied_order_code,
        using=using,
    )
    shipping_vouchers = _collect_scope_offers(
        scope=Voucher.SHIPPING_DISCOUNT,
        vouchers=vouchers,
        redeem_count_map=redeem_count_map,
        subtotal=subtotal,
        shipping_fee_base=shipping_fee_base,
        product_mids=product_mids,
        category_slugs=category_slugs,
        user_id=resolved_user_id,
        applied_code=applied_shipping_code,
        using=using,
    )

    return {
        "order_vouchers": order_vouchers,
        "shipping_vouchers": shipping_vouchers,
        "best_order_voucher_code": order_vouchers[0]["code"] if order_vouchers else None,
        "best_shipping_voucher_code": shipping_vouchers[0]["code"] if shipping_vouchers else None,
        "applied_order_voucher_code": applied_order_code,
        "applied_shipping_voucher_code": applied_shipping_code,
        "evaluated_at": timezone.now().isoformat(),
    }
