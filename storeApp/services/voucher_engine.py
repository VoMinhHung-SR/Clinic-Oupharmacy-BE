from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F

from storeApp.models import Voucher, VoucherRedemption


class VoucherEngineError(Exception):
    def __init__(self, field, message):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

    def to_detail(self):
        return {self.field: [self.message]}


def _reason_to_message(reason_code):
    mapping = {
        Voucher.VALIDATION_INACTIVE: "Voucher is inactive",
        Voucher.VALIDATION_NOT_STARTED: "Voucher is not started",
        Voucher.VALIDATION_EXPIRED: "Voucher is expired",
        Voucher.VALIDATION_USAGE_LIMIT_REACHED: "Voucher usage limit exceeded",
        Voucher.VALIDATION_MISSING_ORDER_SUBTOTAL: "Missing order subtotal",
        Voucher.VALIDATION_MIN_ORDER_NOT_MET: "Minimum order value not met",
        Voucher.VALIDATION_PRODUCT_NOT_APPLICABLE: "Voucher is not applicable to selected products",
        Voucher.VALIDATION_CATEGORY_NOT_APPLICABLE: "Voucher is not applicable to selected categories",
        Voucher.VALIDATION_PER_USER_LIMIT_REACHED: "Per-user limit exceeded",
    }
    return mapping.get(reason_code, "Voucher is not applicable")


def _get_redeem_count_map(user_id, vouchers, using):
    voucher_ids = [voucher.id for voucher in vouchers if voucher]
    if not user_id or not voucher_ids:
        return {}
    rows = (
        VoucherRedemption.objects.using(using)
        .filter(user_id=user_id, voucher_id__in=voucher_ids)
        .values("voucher_id")
        .annotate(total=Count("id"))
    )
    return {row["voucher_id"]: row["total"] for row in rows}


def resolve_voucher_discounts(
    *,
    order_voucher_code,
    shipping_voucher_code,
    order_subtotal,
    shipping_fee_base,
    product_mids,
    category_slugs,
    user_id,
    using="store",
    lock_for_update=True,
):
    requested_codes = [code for code in [order_voucher_code, shipping_voucher_code] if code]
    voucher_by_code = {}
    if requested_codes:
        vouchers = Voucher.objects.using(using).filter(code__in=requested_codes)
        voucher_by_code = {voucher.code: voucher for voucher in vouchers}
        missing_codes = [code for code in requested_codes if code not in voucher_by_code]
        if missing_codes:
            raise VoucherEngineError("voucher_code", f"Voucher not found: {', '.join(missing_codes)}")

    pre_order_voucher = voucher_by_code.get(order_voucher_code) if order_voucher_code else None
    pre_shipping_voucher = voucher_by_code.get(shipping_voucher_code) if shipping_voucher_code else None
    if pre_order_voucher and pre_order_voucher.scope != Voucher.ORDER_DISCOUNT:
        raise VoucherEngineError("order_voucher_code", "order_voucher_code must be ORDER_DISCOUNT voucher")
    if pre_shipping_voucher and pre_shipping_voucher.scope != Voucher.SHIPPING_DISCOUNT:
        raise VoucherEngineError("shipping_voucher_code", "shipping_voucher_code must be SHIPPING_DISCOUNT voucher")

    voucher_ids = sorted([voucher.id for voucher in [pre_order_voucher, pre_shipping_voucher] if voucher])
    voucher_qs = Voucher.objects.using(using).filter(id__in=voucher_ids).order_by("id")
    if lock_for_update:
        voucher_qs = voucher_qs.select_for_update()
    locked_vouchers = voucher_qs
    locked_by_id = {voucher.id: voucher for voucher in locked_vouchers}

    order_voucher = locked_by_id.get(pre_order_voucher.id) if pre_order_voucher else None
    shipping_voucher = locked_by_id.get(pre_shipping_voucher.id) if pre_shipping_voucher else None

    redeem_count_map = _get_redeem_count_map(user_id, [order_voucher, shipping_voucher], using)

    order_discount_amount = Decimal("0")
    shipping_discount_amount = Decimal("0")

    if order_voucher:
        is_valid, reason = order_voucher.validate_for_context(
            order_subtotal=order_subtotal,
            product_mids=product_mids,
            category_slugs=category_slugs,
            user_id=user_id,
            current_user_redeem_count=redeem_count_map.get(order_voucher.id, 0),
            using=using,
        )
        if not is_valid:
            raise VoucherEngineError("order_voucher_code", _reason_to_message(reason))
        order_discount_amount = order_voucher.calculate_discount_for_scope(order_subtotal=order_subtotal)

    if shipping_voucher:
        is_valid, reason = shipping_voucher.validate_for_context(
            order_subtotal=order_subtotal,
            product_mids=product_mids,
            category_slugs=category_slugs,
            user_id=user_id,
            current_user_redeem_count=redeem_count_map.get(shipping_voucher.id, 0),
            using=using,
        )
        if not is_valid:
            raise VoucherEngineError("shipping_voucher_code", _reason_to_message(reason))
        shipping_discount_amount = shipping_voucher.calculate_discount_for_scope(
            order_subtotal=order_subtotal,
            shipping_fee=shipping_fee_base,
        )
        shipping_discount_amount = min(shipping_discount_amount, shipping_fee_base)

    final_shipping_fee = max(Decimal("0"), shipping_fee_base - shipping_discount_amount)
    final_total = max(Decimal("0"), order_subtotal - order_discount_amount + final_shipping_fee)

    return {
        "order_voucher": order_voucher,
        "shipping_voucher": shipping_voucher,
        "order_discount_amount": order_discount_amount,
        "shipping_discount_amount": shipping_discount_amount,
        "final_shipping_fee": final_shipping_fee,
        "final_total": final_total,
    }


def consume_vouchers(*, order, user_id, order_voucher, shipping_voucher, order_discount_amount, shipping_discount_amount, using="store"):
    with transaction.atomic(using=using):
        voucher_updates = [
            (order_voucher, order_discount_amount),
            (shipping_voucher, shipping_discount_amount),
        ]
        for voucher_obj, discount_amount in voucher_updates:
            if not voucher_obj:
                continue
            Voucher.objects.using(using).filter(pk=voucher_obj.pk).update(used_count=F("used_count") + 1)
            VoucherRedemption.objects.using(using).create(
                voucher=voucher_obj,
                order=order,
                user_id=user_id,
                scope=voucher_obj.scope,
                discount_amount=discount_amount,
            )
