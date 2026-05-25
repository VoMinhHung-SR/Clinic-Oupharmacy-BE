from django.core.validators import MinValueValidator
from django.db import models

from mainApp.models import BaseModel


class Cart(BaseModel):
    ACTIVE = "ACTIVE"
    CHECKED_OUT = "CHECKED_OUT"
    ABANDONED = "ABANDONED"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (CHECKED_OUT, "Checked out"),
        (ABANDONED, "Abandoned"),
    ]

    user_id = models.BigIntegerField(db_column="user_id", null=True, blank=True, db_index=True)
    guest_session_id = models.UUIDField(
        db_column="guest_session_id",
        null=True,
        blank=True,
        db_index=True,
        default=None,
        help_text="Anonymous cart session (UUID from X-Guest-Session header)",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE, db_column="status", db_index=True)
    shipping_method = models.ForeignKey(
        "ShippingMethod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="carts",
        db_column="shipping_method_id",
    )
    order_voucher = models.ForeignKey(
        "Voucher",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_discount_carts",
        db_column="order_voucher_id",
    )
    shipping_voucher = models.ForeignKey(
        "Voucher",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shipping_discount_carts",
        db_column="shipping_voucher_id",
    )
    checkout_order = models.ForeignKey(
        "Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_carts",
        db_column="checkout_order_id",
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    shipping_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "store_cart"
        indexes = [
            models.Index(fields=["user_id", "status"]),
            models.Index(fields=["guest_session_id", "status"]),
            models.Index(fields=["status", "updated_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user_id"],
                condition=models.Q(status="ACTIVE", user_id__isnull=False),
                name="store_cart_one_active_per_user",
            ),
            models.UniqueConstraint(
                fields=["guest_session_id"],
                condition=models.Q(status="ACTIVE", guest_session_id__isnull=False),
                name="store_cart_one_active_per_guest",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(user_id__isnull=False, guest_session_id__isnull=True)
                    | models.Q(user_id__isnull=True, guest_session_id__isnull=False)
                ),
                name="store_cart_user_xor_guest",
            ),
        ]


class CartItem(BaseModel):
    cart = models.ForeignKey("Cart", on_delete=models.CASCADE, related_name="items", db_column="cart_id")
    product_variant = models.ForeignKey(
        "ProductVariant",
        on_delete=models.PROTECT,
        related_name="cart_items",
        db_column="product_variant_id",
    )
    product_variant_unit = models.ForeignKey(
        "ProductVariantUnit",
        on_delete=models.PROTECT,
        related_name="cart_items",
        null=True,
        blank=True,
        db_column="product_variant_unit_id",
    )
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    class Meta:
        db_table = "store_cart_item"
        indexes = [
            models.Index(fields=["cart", "updated_date"]),
            models.Index(fields=["product_variant"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product_variant", "product_variant_unit"],
                name="store_cart_item_unique_variant_unit",
            )
        ]
