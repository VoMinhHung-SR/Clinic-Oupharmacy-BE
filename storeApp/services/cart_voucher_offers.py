"""Cart voucher offers for pharmacy storefront (campaign-published + cart context)."""

from decimal import Decimal

from django.utils import timezone

from storeApp.models import Voucher
from storeApp.services.campaign_public import published_displayable_vouchers
from storeApp.services.cart_service import _build_context
from storeApp.services.voucher_engine import _get_redeem_count_map


def _reason_to_display(*, reason, voucher):
    mapping = {
        Voucher.VALIDATION_INACTIVE: "Voucher không còn hiệu lực",
        Voucher.VALIDATION_NOT_STARTED: "Chương trình chưa bắt đầu",
        Voucher.VALIDATION_EXPIRED: "Voucher đã hết hạn",
        Voucher.VALIDATION_USAGE_LIMIT_REACHED: "Voucher đã hết lượt sử dụng",
        Voucher.VALIDATION_MISSING_ORDER_SUBTOTAL: "Giỏ hàng chưa có tổng tiền",
        Voucher.VALIDATION_MIN_ORDER_NOT_MET: None,
        Voucher.VALIDATION_PRODUCT_NOT_APPLICABLE: "Không áp dụng cho sản phẩm trong giỏ",
        Voucher.VALIDATION_CATEGORY_NOT_APPLICABLE: "Không áp dụng cho danh mục trong giỏ",
        Voucher.VALIDATION_PER_USER_LIMIT_REACHED: "Bạn đã dùng hết lượt voucher này",
    }
    if reason == Voucher.VALIDATION_MIN_ORDER_NOT_MET:
        min_value = voucher.min_order_value or Decimal("0")
        if min_value > 0:
            return f"Đơn tối thiểu {int(min_value):,}₫".replace(",", ".")
        return "Chưa đủ giá trị đơn tối thiểu"
    return mapping.get(reason, "Chưa đủ điều kiện áp dụng")


def _serialize_offer(
    *,
    voucher,
    estimated_discount,
    applied_code,
    is_eligible,
    ineligible_reason=None,
):
    return {
        "code": voucher.code,
        "description": voucher.description,
        "type": voucher.type,
        "value": str(voucher.value),
        "scope": voucher.scope,
        "estimated_discount": str(estimated_discount.quantize(Decimal("0.01"))),
        "end_at": voucher.end_at.isoformat() if voucher.end_at else None,
        "is_applied": bool(applied_code and voucher.code == applied_code),
        "is_eligible": is_eligible,
        "ineligible_reason": ineligible_reason,
    }


def _split_primary_unavailable(offers):
    primary = [row for row in offers if row["is_applied"] or row["is_eligible"]]
    unavailable = [row for row in offers if not row["is_eligible"] and not row["is_applied"]]
    return primary, unavailable


def _sort_primary(offers):
    applied = [row for row in offers if row["is_applied"]]
    eligible = sorted(
        [row for row in offers if row["is_eligible"] and not row["is_applied"]],
        key=lambda row: Decimal(row["estimated_discount"]),
        reverse=True,
    )
    return applied + eligible


def _sort_unavailable(offers):
    return sorted(offers, key=lambda row: Decimal(row["value"]), reverse=True)


def _load_voucher_candidates(*, cart, using):
    """Campaign-published vouchers plus any voucher already on the cart."""
    published = published_displayable_vouchers(
        scopes=[Voucher.ORDER_DISCOUNT, Voucher.SHIPPING_DISCOUNT],
        using=using,
    )
    by_id = {voucher.id: voucher for voucher in published}
    for attached in (cart.order_voucher, cart.shipping_voucher):
        if attached is not None and attached.is_active:
            by_id[attached.id] = attached
    return sorted(by_id.values(), key=lambda voucher: (-voucher.value, voucher.code))


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
    seen_codes = set()

    for voucher in vouchers:
        if voucher.scope != scope:
            continue

        is_applied = bool(applied_code and voucher.code == applied_code)
        if not is_applied and not voucher.is_active:
            continue
        if not is_applied and not voucher.is_valid():
            continue

        is_eligible, reason = voucher.validate_for_context(
            order_subtotal=subtotal,
            product_mids=product_mids,
            category_slugs=category_slugs,
            user_id=user_id,
            current_user_redeem_count=redeem_count_map.get(voucher.id, 0),
            using=using,
        )

        estimated_discount = Decimal("0")
        ineligible_reason = None
        if is_eligible:
            estimated_discount = voucher.calculate_discount_for_scope(
                order_subtotal=subtotal,
                shipping_fee=shipping_fee_base,
            )
            if scope == Voucher.SHIPPING_DISCOUNT:
                estimated_discount = min(estimated_discount, shipping_fee_base)
            if estimated_discount <= Decimal("0") and not is_applied:
                is_eligible = False
                ineligible_reason = "Chưa đủ điều kiện áp dụng"
        else:
            ineligible_reason = _reason_to_display(reason=reason, voucher=voucher)

        offers.append(
            _serialize_offer(
                voucher=voucher,
                estimated_discount=estimated_discount if is_eligible else Decimal("0"),
                applied_code=applied_code,
                is_eligible=is_eligible,
                ineligible_reason=ineligible_reason if not is_eligible else None,
            )
        )
        seen_codes.add(voucher.code)

    if applied_code and applied_code not in seen_codes:
        applied_voucher = next((v for v in vouchers if v.code == applied_code and v.scope == scope), None)
        if applied_voucher is not None:
            is_eligible, reason = applied_voucher.validate_for_context(
                order_subtotal=subtotal,
                product_mids=product_mids,
                category_slugs=category_slugs,
                user_id=user_id,
                current_user_redeem_count=redeem_count_map.get(applied_voucher.id, 0),
                using=using,
            )
            discount = Decimal("0")
            ineligible_reason = None
            if is_eligible:
                discount = applied_voucher.calculate_discount_for_scope(
                    order_subtotal=subtotal,
                    shipping_fee=shipping_fee_base,
                )
                if scope == Voucher.SHIPPING_DISCOUNT:
                    discount = min(discount, shipping_fee_base)
            else:
                ineligible_reason = _reason_to_display(reason=reason, voucher=applied_voucher)
            offers.insert(
                0,
                _serialize_offer(
                    voucher=applied_voucher,
                    estimated_discount=max(Decimal("0"), discount),
                    applied_code=applied_code,
                    is_eligible=is_eligible,
                    ineligible_reason=ineligible_reason,
                ),
            )

    primary, unavailable = _split_primary_unavailable(offers)
    return _sort_primary(primary), _sort_unavailable(unavailable)


def list_cart_voucher_offers(*, cart, user_id=None, using="store", item_ids=None):
    """
    Campaign-published vouchers for cart offer UI.

    Primary lists contain applied + eligible rows; unavailable rows are separated for optional expand in FE.
    """
    _, subtotal, shipping_fee_base, product_mids, category_slugs, _ = _build_context(
        cart=cart,
        using=using,
        item_ids=item_ids,
    )
    applied_order_code = cart.order_voucher.code if cart.order_voucher else None
    applied_shipping_code = cart.shipping_voucher.code if cart.shipping_voucher else None
    resolved_user_id = user_id or cart.user_id

    vouchers = _load_voucher_candidates(cart=cart, using=using)
    redeem_count_map = _get_redeem_count_map(resolved_user_id, vouchers, using)

    order_primary, order_unavailable = _collect_scope_offers(
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
    shipping_primary, shipping_unavailable = _collect_scope_offers(
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

    eligible_order = sorted(
        [row for row in order_primary if row["is_eligible"]],
        key=lambda row: Decimal(row["estimated_discount"]),
        reverse=True,
    )
    eligible_shipping = sorted(
        [row for row in shipping_primary if row["is_eligible"]],
        key=lambda row: Decimal(row["estimated_discount"]),
        reverse=True,
    )

    return {
        "order_vouchers": order_primary,
        "order_vouchers_unavailable": order_unavailable,
        "shipping_vouchers": shipping_primary,
        "shipping_vouchers_unavailable": shipping_unavailable,
        "best_order_voucher_code": eligible_order[0]["code"] if eligible_order else None,
        "best_shipping_voucher_code": eligible_shipping[0]["code"] if eligible_shipping else None,
        "applied_order_voucher_code": applied_order_code,
        "applied_shipping_voucher_code": applied_shipping_code,
        "evaluated_at": timezone.now().isoformat(),
    }
