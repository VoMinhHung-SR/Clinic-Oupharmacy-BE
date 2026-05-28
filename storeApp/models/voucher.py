from decimal import Decimal, InvalidOperation

from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

from mainApp.models import BaseModel


class Voucher(BaseModel):
    """Model quản lý voucher/giảm giá"""

    ORDER_DISCOUNT = "ORDER_DISCOUNT"
    SHIPPING_DISCOUNT = "SHIPPING_DISCOUNT"
    SCOPE_CHOICES = [
        (ORDER_DISCOUNT, "Order Discount"),
        (SHIPPING_DISCOUNT, "Shipping Discount"),
    ]
    VALIDATION_INACTIVE = "inactive"
    VALIDATION_NOT_STARTED = "not_started"
    VALIDATION_EXPIRED = "expired"
    VALIDATION_USAGE_LIMIT_REACHED = "usage_limit_reached"
    VALIDATION_MISSING_ORDER_SUBTOTAL = "missing_order_subtotal"
    VALIDATION_MIN_ORDER_NOT_MET = "min_order_not_met"
    VALIDATION_PRODUCT_NOT_APPLICABLE = "product_not_applicable"
    VALIDATION_CATEGORY_NOT_APPLICABLE = "category_not_applicable"
    VALIDATION_PER_USER_LIMIT_REACHED = "per_user_limit_reached"
    VALIDATION_OK = "ok"

    code = models.CharField(max_length=50, null=False, blank=False, unique=True, db_index=True)
    type = models.CharField(max_length=10, choices=[("FIXED", "Fixed Amount"), ("PERCENT", "Percentage")], default="PERCENT")
    scope = models.CharField(max_length=30, choices=SCOPE_CHOICES, default=ORDER_DISCOUNT, db_index=True)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=False, default=0)
    max_discount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_order_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    applicable_products = models.JSONField(default=list, blank=True)
    applicable_categories = models.JSONField(default=list, blank=True)
    start_at = models.DateTimeField(null=True, blank=True, db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)
    usage_limit = models.IntegerField(null=True, blank=True)
    per_user_limit = models.IntegerField(null=True, blank=True)
    used_count = models.IntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.CharField(max_length=255, null=True, blank=True)

    @staticmethod
    def _to_decimal(value, default="0"):
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal(default)

    @staticmethod
    def _extract_order_item_context(order):
        if not order:
            return set(), set()

        product_mids = set()
        category_slugs = set()
        from storeApp.services.product_category_helpers import collect_category_slugs_for_product

        items_qs = (
            order.items.select_related("product_variant__product__category")
            .prefetch_related("product_variant__product__product_categories__category")
            .all()
        )
        for item in items_qs:
            product = getattr(getattr(item, "product_variant", None), "product", None)
            if not product:
                continue
            if product.mid:
                product_mids.add(product.mid)
            category_slugs.update(collect_category_slugs_for_product(product))
        return product_mids, category_slugs

    def is_valid(self):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False
        return True

    def validate_for_context(
        self,
        order_subtotal=None,
        product_mids=None,
        category_slugs=None,
        user_id=None,
        current_user_redeem_count=None,
        using=None,
    ):
        if not self.is_active:
            return False, self.VALIDATION_INACTIVE

        now = timezone.now()
        if self.start_at and now < self.start_at:
            return False, self.VALIDATION_NOT_STARTED
        if self.end_at and now > self.end_at:
            return False, self.VALIDATION_EXPIRED
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, self.VALIDATION_USAGE_LIMIT_REACHED

        if order_subtotal is None:
            return False, self.VALIDATION_MISSING_ORDER_SUBTOTAL

        order_value = self._to_decimal(order_subtotal)
        min_order_value = self._to_decimal(self.min_order_value)
        if min_order_value and order_value < min_order_value:
            return False, self.VALIDATION_MIN_ORDER_NOT_MET

        product_mids = product_mids or set()
        category_slugs = category_slugs or set()

        if self.applicable_products:
            applicable_products = {str(mid) for mid in self.applicable_products}
            if not product_mids.intersection(applicable_products):
                return False, self.VALIDATION_PRODUCT_NOT_APPLICABLE

        if self.applicable_categories:
            applicable_categories = {str(slug) for slug in self.applicable_categories}
            if not category_slugs.intersection(applicable_categories):
                return False, self.VALIDATION_CATEGORY_NOT_APPLICABLE

        if not self.can_user_redeem(
            user_id=user_id,
            current_count=current_user_redeem_count,
            using=using,
        ):
            return False, self.VALIDATION_PER_USER_LIMIT_REACHED

        return True, self.VALIDATION_OK

    def is_applicable_to_context(self, order_subtotal=None, product_mids=None, category_slugs=None):
        is_valid, _ = self.validate_for_context(
            order_subtotal=order_subtotal,
            product_mids=product_mids,
            category_slugs=category_slugs,
        )
        return is_valid

    def is_applicable(self, order):
        if order is None:
            return False
        product_mids, category_slugs = self._extract_order_item_context(order)
        return self.is_applicable_to_context(
            order_subtotal=getattr(order, "subtotal", None),
            product_mids=product_mids,
            category_slugs=category_slugs,
        )

    def can_user_redeem(self, user_id, current_count=None, using=None):
        if not user_id or not self.per_user_limit:
            return True
        if current_count is None:
            db = using or getattr(self._state, "db", None) or "default"
            current_count = VoucherRedemption.objects.using(db).filter(
                voucher_id=self.id,
                user_id=user_id,
            ).count()
        return current_count < self.per_user_limit

    def calculate_discount(self, original_price):
        order_amount = self._to_decimal(original_price)
        if order_amount <= Decimal("0"):
            return Decimal("0")

        if self.type == "PERCENT":
            voucher_value = self._to_decimal(self.value)
            discount = order_amount * (voucher_value / Decimal("100"))
            if self.max_discount is not None:
                discount = min(discount, self._to_decimal(self.max_discount))
            return max(Decimal("0"), discount)

        fixed_discount = self._to_decimal(self.value)
        return max(Decimal("0"), min(fixed_discount, order_amount))

    def calculate_discount_for_scope(self, order_subtotal, shipping_fee=None):
        if self.scope == self.SHIPPING_DISCOUNT:
            shipping_amount = self._to_decimal(shipping_fee)
            return self.calculate_discount(shipping_amount)
        return self.calculate_discount(self._to_decimal(order_subtotal))

    def apply_voucher(self, order):
        if not self.is_applicable(order):
            return Decimal("0")
        order_value = self._to_decimal(getattr(order, "subtotal", None))
        return self.calculate_discount(order_value)

    def increment_used_count(self, using=None):
        db = using or getattr(self._state, "db", None) or "default"
        with transaction.atomic(using=db):
            locked_voucher = Voucher.objects.using(db).select_for_update().get(pk=self.pk)
            if not locked_voucher.is_valid():
                return False
            locked_voucher.used_count = F("used_count") + 1
            locked_voucher.save(update_fields=["used_count"])
            locked_voucher.refresh_from_db(fields=["used_count"])
            self.used_count = locked_voucher.used_count
            return True

    def __str__(self):
        if self.type == "PERCENT":
            return f"{self.code} - {self.value}% off"
        return f"{self.code} - {self.value:,.0f}₫ off"

    class Meta:
        db_table = "store_voucher"
        verbose_name = "Voucher"
        verbose_name_plural = "Vouchers"
        ordering = ["-created_date"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["scope", "is_active", "start_at", "end_at"]),
            models.Index(fields=["is_active", "start_at", "end_at"]),
            models.Index(fields=["used_count", "usage_limit"]),
        ]


class VoucherRedemption(BaseModel):
    voucher = models.ForeignKey("Voucher", on_delete=models.CASCADE, related_name="redemptions", db_column="voucher_id")
    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name="voucher_redemptions", db_column="order_id")
    user_id = models.BigIntegerField(null=False, db_column="user_id")
    scope = models.CharField(max_length=30, choices=Voucher.SCOPE_CHOICES, db_column="scope")
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        default=0,
        validators=[MinValueValidator(0)],
        db_column="discount_amount",
    )

    class Meta:
        db_table = "store_voucher_redemption"
        verbose_name = "Voucher Redemption"
        verbose_name_plural = "Voucher Redemptions"
        indexes = [
            models.Index(fields=["voucher", "user_id"]),
            models.Index(fields=["order"]),
            models.Index(fields=["user_id", "created_date"]),
        ]
