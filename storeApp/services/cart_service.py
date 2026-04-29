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
    if product_variant_unit_id:
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


def _build_context(*, cart, using="store"):
    items = list(
        cart.items.using(using)
        .select_related("product_variant__product__category", "product_variant_unit")
        .all()
    )
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


def recalculate_cart(*, cart, using="store", expected_version=None):
    _assert_cart_version(cart=cart, expected_version=expected_version)
    items, subtotal, shipping_fee_base, product_mids, category_slugs = _build_context(cart=cart, using=using)
    if not items:
        cart.subtotal = Decimal("0")
        cart.shipping_fee = Decimal("0")
        cart.discount_amount = Decimal("0")
        cart.shipping_discount_amount = Decimal("0")
        cart.total = Decimal("0")
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
    cart.subtotal = subtotal
    cart.shipping_fee = voucher_result["final_shipping_fee"]
    cart.discount_amount = voucher_result["order_discount_amount"]
    cart.shipping_discount_amount = voucher_result["shipping_discount_amount"]
    cart.total = voucher_result["final_total"]
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


def checkout_cart(*, cart, payment_method, shipping_address, notes=None, using="store", expected_version=None):
    from storeApp.models import Order, OrderItem

    with transaction.atomic(using=using):
        locked_cart = (
            Cart.objects.using(using)
            .select_related("shipping_method", "order_voucher", "shipping_voucher")
            .select_for_update()
            .get(id=cart.id)
        )
        _assert_cart_version(cart=locked_cart, expected_version=expected_version)
        if locked_cart.status != Cart.ACTIVE:
            raise CartServiceError("Cart is not active")
        if not locked_cart.shipping_method:
            raise CartServiceError("Shipping method is required before checkout")

        items, subtotal, shipping_fee_base, product_mids, category_slugs = _build_context(cart=locked_cart, using=using)
        if not items:
            raise CartServiceError("Cart must have at least one item")

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
            required_base_quantity = int(item.quantity) * int(item.product_variant_unit.quantity_in_base)
            deduct_stock(item.product_variant_id, required_base_quantity)

        consume_vouchers(
            order=order,
            user_id=locked_cart.user_id,
            order_voucher=voucher_result["order_voucher"],
            shipping_voucher=voucher_result["shipping_voucher"],
            order_discount_amount=voucher_result["order_discount_amount"],
            shipping_discount_amount=voucher_result["shipping_discount_amount"],
            using=using,
        )

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
