from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F

from storeApp.models import Cart, CartItem, ProductVariant, ProductVariantUnit
from storeApp.services.cart_cache import get_cart_cache_gateway
from storeApp.services.stock import get_available_stock, deduct_stock
from storeApp.services.voucher_engine import VoucherEngineError, resolve_voucher_discounts, consume_vouchers


class CartServiceError(Exception):
    pass


class CartVersionConflictError(CartServiceError):
    def __init__(self, *, expected_version, current_version):
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(f"Cart version mismatch. expected={expected_version}, current={current_version}")


def _invalidate_cart_related_cache(*, cart, order_voucher_code=None, shipping_voucher_code=None):
    cache_gateway = get_cart_cache_gateway()
    cache_gateway.invalidate_cart_summary(cart_id=cart.id)
    cache_gateway.invalidate_user_active_cart(user_id=cart.user_id)
    for code in (order_voucher_code, shipping_voucher_code):
        if code:
            cache_gateway.invalidate_voucher_light(voucher_code=code)


def _to_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise CartServiceError("Invalid decimal value")


def get_or_create_active_cart(*, user_id, using="store"):
    cart = (
        Cart.objects.using(using)
        .select_related("shipping_method", "order_voucher", "shipping_voucher")
        .filter(user_id=user_id, status=Cart.ACTIVE)
        .first()
    )
    if cart:
        return cart
    return Cart.objects.using(using).create(user_id=user_id, status=Cart.ACTIVE)


def _assert_cart_version(*, cart, expected_version):
    if expected_version is None:
        raise CartServiceError("expected_version is required")
    if cart.version != expected_version:
        raise CartVersionConflictError(expected_version=expected_version, current_version=cart.version)


def _resolve_unit(*, product_variant, product_variant_unit_id=None, using="store"):
    if product_variant_unit_id is not None:
        try:
            return ProductVariantUnit.objects.using(using).get(
                id=product_variant_unit_id,
                variant_id=product_variant.id,
                is_published=True,
            )
        except ProductVariantUnit.DoesNotExist as exc:
            raise CartServiceError("ProductVariantUnit not found for this variant") from exc
    unit = (
        ProductVariantUnit.objects.using(using)
        .filter(variant_id=product_variant.id, is_default=True, is_published=True)
        .first()
    ) or (
        ProductVariantUnit.objects.using(using)
        .filter(variant_id=product_variant.id, is_published=True)
        .order_by("unit_order", "id")
        .first()
    )
    if not unit:
        raise CartServiceError("No published ProductVariantUnit for this variant")
    return unit


def add_or_update_item(
    *,
    cart,
    product_variant_id,
    quantity,
    product_variant_unit_id=None,
    using="store",
):
    if quantity <= 0:
        raise CartServiceError("quantity must be greater than 0")

    try:
        product_variant = ProductVariant.objects.using(using).select_related("product__category").get(
            id=product_variant_id,
            active=True,
        )
    except ProductVariant.DoesNotExist as exc:
        raise CartServiceError("ProductVariant not found or inactive") from exc

    unit = _resolve_unit(
        product_variant=product_variant,
        product_variant_unit_id=product_variant_unit_id,
        using=using,
    )

    unit_price = _to_decimal(unit.price_value)
    required_base_quantity = int(quantity) * int(unit.quantity_in_base)
    total_available = get_available_stock(product_variant.id)
    if total_available < required_base_quantity:
        raise CartServiceError(
            f"Insufficient stock in base unit. Available: {total_available}, Requested: {required_base_quantity}"
        )

    item, _ = CartItem.objects.using(using).update_or_create(
        cart_id=cart.id,
        product_variant_id=product_variant.id,
        product_variant_unit_id=unit.id,
        defaults={
            "quantity": int(quantity),
            "unit_price_snapshot": unit_price,
        },
    )
    _invalidate_cart_related_cache(
        cart=cart,
        order_voucher_code=getattr(cart.order_voucher, "code", None),
        shipping_voucher_code=getattr(cart.shipping_voucher, "code", None),
    )
    return item


def remove_item(*, cart, item_id, using="store"):
    deleted, _ = CartItem.objects.using(using).filter(cart_id=cart.id, id=item_id).delete()
    if not deleted:
        raise CartServiceError("Cart item not found")
    _invalidate_cart_related_cache(
        cart=cart,
        order_voucher_code=getattr(cart.order_voucher, "code", None),
        shipping_voucher_code=getattr(cart.shipping_voucher, "code", None),
    )


def update_item(
    *,
    cart,
    item_id,
    quantity=None,
    product_variant_unit_id=None,
    using="store",
):
    item = (
        CartItem.objects.using(using)
        .select_related("product_variant__product__category", "product_variant_unit")
        .filter(cart_id=cart.id, id=item_id)
        .first()
    )
    if not item:
        raise CartServiceError("Cart item not found")

    if quantity is None and product_variant_unit_id is None:
        raise CartServiceError("At least one of quantity or product_variant_unit_id is required")

    next_quantity = int(item.quantity) if quantity is None else int(quantity)
    if next_quantity <= 0:
        raise CartServiceError("quantity must be greater than 0")

    next_unit = item.product_variant_unit or _resolve_unit(
        product_variant=item.product_variant,
        using=using,
    )
    if product_variant_unit_id is not None:
        next_unit = _resolve_unit(
            product_variant=item.product_variant,
            product_variant_unit_id=product_variant_unit_id,
            using=using,
        )

    existing_same_unit = (
        CartItem.objects.using(using)
        .filter(
            cart_id=cart.id,
            product_variant_id=item.product_variant_id,
            product_variant_unit_id=next_unit.id,
        )
        .exclude(id=item.id)
        .first()
    )
    final_quantity = next_quantity + int(existing_same_unit.quantity) if existing_same_unit else next_quantity
    required_base_quantity = final_quantity * int(next_unit.quantity_in_base)
    total_available = get_available_stock(item.product_variant_id)
    if total_available < required_base_quantity:
        raise CartServiceError(
            f"Insufficient stock in base unit. Available: {total_available}, Requested: {required_base_quantity}"
        )

    unit_price = _to_decimal(next_unit.price_value)
    if existing_same_unit:
        existing_same_unit.quantity = final_quantity
        existing_same_unit.unit_price_snapshot = unit_price
        existing_same_unit.save(update_fields=["quantity", "unit_price_snapshot"])
        item.delete()
        updated_item = existing_same_unit
    else:
        update_fields = []
        if int(item.quantity) != next_quantity:
            item.quantity = next_quantity
            update_fields.append("quantity")
        if item.product_variant_unit_id != next_unit.id:
            item.product_variant_unit = next_unit
            update_fields.append("product_variant_unit")
        if _to_decimal(item.unit_price_snapshot) != unit_price:
            item.unit_price_snapshot = unit_price
            update_fields.append("unit_price_snapshot")
        if update_fields:
            item.save(update_fields=update_fields)
        updated_item = item

    _invalidate_cart_related_cache(
        cart=cart,
        order_voucher_code=getattr(cart.order_voucher, "code", None),
        shipping_voucher_code=getattr(cart.shipping_voucher, "code", None),
    )
    return updated_item


def _build_context(*, cart, using="store", item_ids=None):
    """
    Summarize cart lines for totals / voucher context.

    item_ids: optional list of CartItem primary keys to include. When provided, must be
    non-empty and every id must belong to this cart (otherwise CartServiceError).
    When None, all lines are included (default checkout behavior).
    """
    qs = cart.items.using(using).select_related("product_variant__product__category", "product_variant_unit")
    if item_ids is not None:
        unique_ids = []
        seen_ids = set()
        for raw_id in item_ids:
            try:
                parsed_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise CartServiceError("cart_item_ids must contain only integers") from exc
            if parsed_id in seen_ids:
                continue
            seen_ids.add(parsed_id)
            unique_ids.append(parsed_id)
        if len(unique_ids) == 0:
            raise CartServiceError("cart_item_ids cannot be empty")
        items = list(qs.filter(id__in=unique_ids))
        found = {int(i.id) for i in items}
        if found != seen_ids:
            raise CartServiceError("One or more cart_item_ids are invalid for this cart")
    else:
        items = list(qs.all())
    subtotal = Decimal("0")
    product_mids = set()
    category_slugs = set()

    for item in items:
        unit_price = _to_decimal(item.unit_price_snapshot or item.product_variant_unit.price_value)
        subtotal += unit_price * item.quantity
        if item.product_variant.product and item.product_variant.product.mid:
            product_mids.add(str(item.product_variant.product.mid))
        category = getattr(item.product_variant.product, "category", None)
        if category and category.slug:
            category_slugs.add(str(category.slug))

    shipping_fee_base = Decimal(str(cart.shipping_method.price)) if cart.shipping_method else Decimal("0")
    return items, subtotal, shipping_fee_base, product_mids, category_slugs


def _item_required_base_quantity(item) -> int:
    unit = item.product_variant_unit
    if not unit:
        raise CartServiceError("Cart item is missing product_variant_unit")
    return int(item.quantity) * int(unit.quantity_in_base)


def _assert_checkout_stock(*, items, using="store"):
    """Ensure batch stock (base unit) covers all checkout lines; aggregate per variant."""
    required_by_variant: dict[int, int] = {}
    for item in items:
        variant_id = int(item.product_variant_id)
        required_by_variant[variant_id] = required_by_variant.get(variant_id, 0) + _item_required_base_quantity(item)

    for variant_id, required_base_quantity in required_by_variant.items():
        total_available = get_available_stock(variant_id)
        if total_available < required_base_quantity:
            raise CartServiceError(
                f"Insufficient stock in base unit. Available: {total_available}, "
                f"Requested: {required_base_quantity} (product_variant_id={variant_id})"
            )


def recalculate_cart(*, cart, using="store", expected_version=None):
    _assert_cart_version(cart=cart, expected_version=expected_version)
    items, subtotal, shipping_fee_base, product_mids, category_slugs = _build_context(cart=cart, using=using)
    if not items:
        zero = Decimal("0")
        if (
            cart.subtotal == zero
            and cart.shipping_fee == zero
            and cart.discount_amount == zero
            and cart.shipping_discount_amount == zero
            and cart.total == zero
        ):
            return cart
        cart.subtotal = zero
        cart.shipping_fee = zero
        cart.discount_amount = zero
        cart.shipping_discount_amount = zero
        cart.total = zero
        cart.version = F("version") + 1
        cart.save(
            update_fields=[
                "subtotal",
                "shipping_fee",
                "discount_amount",
                "shipping_discount_amount",
                "total",
                "version",
            ]
        )
        cart.refresh_from_db()
        _invalidate_cart_related_cache(cart=cart)
        return cart

    voucher_result = resolve_voucher_discounts(
        order_voucher_code=cart.order_voucher.code if cart.order_voucher else None,
        shipping_voucher_code=cart.shipping_voucher.code if cart.shipping_voucher else None,
        order_subtotal=subtotal,
        shipping_fee_base=shipping_fee_base,
        product_mids=product_mids,
        category_slugs=category_slugs,
        user_id=cart.user_id,
        using=using,
        lock_for_update=False,
    )
    new_shipping_fee = voucher_result["final_shipping_fee"]
    new_discount = voucher_result["order_discount_amount"]
    new_shipping_discount = voucher_result["shipping_discount_amount"]
    new_total = voucher_result["final_total"]
    if (
        cart.subtotal == subtotal
        and cart.shipping_fee == new_shipping_fee
        and cart.discount_amount == new_discount
        and cart.shipping_discount_amount == new_shipping_discount
        and cart.total == new_total
    ):
        return cart
    cart.subtotal = subtotal
    cart.shipping_fee = new_shipping_fee
    cart.discount_amount = new_discount
    cart.shipping_discount_amount = new_shipping_discount
    cart.total = new_total
    cart.version = F("version") + 1
    cart.save(
        update_fields=[
            "subtotal",
            "shipping_fee",
            "discount_amount",
            "shipping_discount_amount",
            "total",
            "version",
        ]
    )
    cart.refresh_from_db()
    _invalidate_cart_related_cache(
        cart=cart,
        order_voucher_code=voucher_result["order_voucher"].code if voucher_result["order_voucher"] else None,
        shipping_voucher_code=voucher_result["shipping_voucher"].code if voucher_result["shipping_voucher"] else None,
    )
    return cart


def set_cart_shipping_method(*, cart_id, shipping_method, expected_version, using="store"):
    """Atomically set shipping after version check; avoids applying shipping when optimistic lock fails."""
    with transaction.atomic(using=using):
        cart = Cart.objects.using(using).select_for_update(of=("self",)).get(id=cart_id)
        _assert_cart_version(cart=cart, expected_version=expected_version)
        cart.shipping_method = shipping_method
        cart.save(update_fields=["shipping_method"])
        return recalculate_cart(cart=cart, using=using, expected_version=cart.version)


def checkout_cart(
    *,
    cart,
    payment_method,
    shipping_address,
    notes=None,
    using="store",
    expected_version=None,
    checkout_item_ids=None,
):
    from storeApp.models import Order, OrderItem

    with transaction.atomic(using=using):
        locked_cart = (
            Cart.objects.using(using)
            .select_related("shipping_method", "order_voucher", "shipping_voucher")
            .select_for_update(of=("self",))
            .get(id=cart.id)
        )
        _assert_cart_version(cart=locked_cart, expected_version=expected_version)
        if locked_cart.status != Cart.ACTIVE:
            raise CartServiceError("Cart is not active")
        if not locked_cart.shipping_method:
            raise CartServiceError("Shipping method is required before checkout")

        items, subtotal, shipping_fee_base, product_mids, category_slugs = _build_context(
            cart=locked_cart, using=using, item_ids=checkout_item_ids
        )
        if not items:
            raise CartServiceError("Cart must have at least one item")

        _assert_checkout_stock(items=items, using=using)

        voucher_result = resolve_voucher_discounts(
            order_voucher_code=locked_cart.order_voucher.code if locked_cart.order_voucher else None,
            shipping_voucher_code=locked_cart.shipping_voucher.code if locked_cart.shipping_voucher else None,
            order_subtotal=subtotal,
            shipping_fee_base=shipping_fee_base,
            product_mids=product_mids,
            category_slugs=category_slugs,
            user_id=locked_cart.user_id,
            using=using,
            lock_for_update=True,
        )

        order = Order.objects.using(using).create(
            user_id=locked_cart.user_id,
            shipping_address=shipping_address,
            shipping_method=locked_cart.shipping_method,
            payment_method=payment_method,
            subtotal=subtotal,
            shipping_fee=voucher_result["final_shipping_fee"],
            total=voucher_result["final_total"],
            notes=notes,
            order_voucher=voucher_result["order_voucher"],
            shipping_voucher=voucher_result["shipping_voucher"],
            discount_amount=voucher_result["order_discount_amount"],
            shipping_discount_amount=voucher_result["shipping_discount_amount"],
        )

        for item in items:
            OrderItem.objects.using(using).create(
                order=order,
                product_variant=item.product_variant,
                product_variant_unit=item.product_variant_unit,
                quantity=item.quantity,
                price=item.unit_price_snapshot,
            )
            required_base_quantity = _item_required_base_quantity(item)
            try:
                deduct_stock(item.product_variant_id, required_base_quantity)
            except ValueError as exc:
                raise CartServiceError(str(exc)) from exc

        consume_vouchers(
            order=order,
            user_id=locked_cart.user_id,
            order_voucher=voucher_result["order_voucher"],
            shipping_voucher=voucher_result["shipping_voucher"],
            order_discount_amount=voucher_result["order_discount_amount"],
            shipping_discount_amount=voucher_result["shipping_discount_amount"],
            using=using,
        )

        paid_line_ids = [item.id for item in items]
        CartItem.objects.using(using).filter(cart_id=locked_cart.id, id__in=paid_line_ids).delete()
        remaining_exists = CartItem.objects.using(using).filter(cart_id=locked_cart.id).exists()

        if remaining_exists:
            locked_cart.checkout_order = None
            locked_cart.status = Cart.ACTIVE
            locked_cart.save(update_fields=["checkout_order", "status"])
            recalculate_cart(cart=locked_cart, using=using, expected_version=locked_cart.version)
        else:
            locked_cart.status = Cart.CHECKED_OUT
            locked_cart.checkout_order = order
            locked_cart.subtotal = subtotal
            locked_cart.shipping_fee = voucher_result["final_shipping_fee"]
            locked_cart.discount_amount = voucher_result["order_discount_amount"]
            locked_cart.shipping_discount_amount = voucher_result["shipping_discount_amount"]
            locked_cart.total = voucher_result["final_total"]
            locked_cart.save(
                update_fields=[
                    "status",
                    "checkout_order",
                    "subtotal",
                    "shipping_fee",
                    "discount_amount",
                    "shipping_discount_amount",
                    "total",
                ]
            )
        _invalidate_cart_related_cache(
            cart=locked_cart,
            order_voucher_code=voucher_result["order_voucher"].code if voucher_result["order_voucher"] else None,
            shipping_voucher_code=voucher_result["shipping_voucher"].code if voucher_result["shipping_voucher"] else None,
        )
        return order
