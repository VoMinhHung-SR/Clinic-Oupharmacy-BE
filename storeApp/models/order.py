from django.core.validators import MinValueValidator
from django.db import IntegrityError, models

from mainApp.models import BaseModel


class ShippingMethod(BaseModel):
    """Phương thức vận chuyển"""

    name = models.CharField(max_length=120, null=False, blank=False, db_column="name")
    price = models.FloatField(null=False, default=0, validators=[MinValueValidator(0)], db_column="price")
    estimated_days = models.IntegerField(
        null=True,
        blank=True,
        db_column="estimated_days",
        help_text="Số ngày ước tính",
    )
    active = models.BooleanField(default=True, db_column="active")

    def __str__(self):
        return f"{self.name} - {self.price:,.0f}₫"

    class Meta:
        db_table = "store_shipping_method"
        verbose_name = "Shipping Method"
        verbose_name_plural = "Shipping Methods"


class PaymentMethod(BaseModel):
    """Phương thức thanh toán"""

    name = models.CharField(max_length=120, null=False, blank=False, db_column="name")
    code = models.CharField(
        max_length=60,
        null=False,
        blank=False,
        unique=True,
        db_column="code",
        help_text="Mã định danh: COD, MOMO, VNPAY...",
    )
    active = models.BooleanField(default=True, db_column="active")

    def __str__(self):
        return self.name

    class Meta:
        db_table = "store_payment_method"
        verbose_name = "Payment Method"
        verbose_name_plural = "Payment Methods"


class Order(BaseModel):
    """Đơn hàng online"""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    SHIPPING = "SHIPPING"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (PENDING, "Chờ xử lý"),
        (CONFIRMED, "Đã xác nhận"),
        (SHIPPING, "Đang giao hàng"),
        (DELIVERED, "Đã giao"),
        (CANCELLED, "Đã hủy"),
    ]

    order_number = models.CharField(
        max_length=30,
        null=False,
        blank=False,
        unique=True,
        db_index=True,
        db_column="order_number",
    )
    user_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_column="user_id",
        help_text="ID của User trong database default",
    )
    shipping_address = models.TextField(null=False, blank=False, db_column="shipping_address")
    shipping_method = models.ForeignKey(
        ShippingMethod,
        on_delete=models.PROTECT,
        related_name="orders",
        db_column="shipping_method_id",
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        related_name="orders",
        db_column="payment_method_id",
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        default=0,
        validators=[MinValueValidator(0)],
        db_column="subtotal",
        help_text="Tổng tiền sản phẩm",
    )
    shipping_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        default=0,
        validators=[MinValueValidator(0)],
        db_column="shipping_fee",
        help_text="Phí vận chuyển",
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        default=0,
        validators=[MinValueValidator(0)],
        db_column="total",
        help_text="Tổng thanh toán",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_column="status")
    notes = models.TextField(null=True, blank=True, db_column="notes", help_text="Ghi chú của khách hàng")
    order_voucher = models.ForeignKey(
        "Voucher",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_discount_orders",
        db_column="order_voucher_id",
    )
    shipping_voucher = models.ForeignKey(
        "Voucher",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shipping_discount_orders",
        db_column="shipping_voucher_id",
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        default=0,
        validators=[MinValueValidator(0)],
        db_column="discount_amount",
        help_text="Số tiền giảm từ voucher giảm đơn",
    )
    shipping_discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        default=0,
        validators=[MinValueValidator(0)],
        db_column="shipping_discount_amount",
        help_text="Số tiền giảm từ voucher giảm phí ship",
    )

    def save(self, *args, **kwargs):
        if self.order_number:
            return super().save(*args, **kwargs)

        for attempt in range(5):
            self.order_number = self.generate_order_number()
            try:
                return super().save(*args, **kwargs)
            except IntegrityError as exc:
                if "order_number" in str(exc) and attempt < 4:
                    continue
                raise

    @staticmethod
    def generate_order_number():
        from django.utils import timezone as tz

        today = tz.localtime(tz.now())
        date_str = today.strftime("%Y%m%d")
        last_order = Order.objects.filter(order_number__startswith=f"ORD{date_str}").order_by("-order_number").first()
        if last_order:
            last_num = int(last_order.order_number[-4:])
            new_num = last_num + 1
        else:
            new_num = 1
        return f"ORD{date_str}{new_num:04d}"

    def __str__(self):
        return f"Đơn hàng {self.order_number} - {self.get_status_display()}"

    class Meta:
        db_table = "store_order"
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-created_date"]


class OrderItem(BaseModel):
    """Chi tiết đơn hàng"""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", db_column="order_id")
    product_variant = models.ForeignKey(
        "ProductVariant",
        on_delete=models.PROTECT,
        related_name="order_items",
        db_column="product_variant_id",
    )
    product_variant_unit = models.ForeignKey(
        "ProductVariantUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
        db_column="product_variant_unit_id",
        help_text="Đơn vị bán đã chọn (Hộp/Lọ/...); null = dữ liệu cũ hoặc mặc định theo variant",
    )
    quantity = models.PositiveIntegerField(null=False, validators=[MinValueValidator(1)], db_column="quantity")
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        validators=[MinValueValidator(0)],
        db_column="price",
        help_text="Đơn giá snapshot theo đơn vị đã chọn (ProductVariantUnit)",
    )

    @property
    def subtotal(self):
        if self.quantity is None or self.price is None:
            return 0
        return float(self.quantity) * float(self.price)

    def __str__(self):
        return f"{self.order.order_number} - Sản phẩm: {self.product_variant} x{self.quantity}"

    class Meta:
        db_table = "store_order_item"
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
        ordering = ["created_date"]
