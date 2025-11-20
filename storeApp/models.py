from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from mainApp.models import BaseModel


class Brand(BaseModel):
    """Thương hiệu sản phẩm"""
    name = models.CharField(max_length=120, null=False, blank=False, unique=True, db_column='name')
    active = models.BooleanField(default=True, db_column='active')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'store_brand'
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'


class ShippingMethod(BaseModel):
    """Phương thức vận chuyển"""
    name = models.CharField(max_length=120, null=False, blank=False, db_column='name')
    price = models.FloatField(null=False, default=0, validators=[MinValueValidator(0)], db_column='price')
    estimated_days = models.IntegerField(null=True, blank=True, db_column='estimated_days', help_text="Số ngày ước tính")
    active = models.BooleanField(default=True, db_column='active')

    def __str__(self):
        return f"{self.name} - {self.price:,.0f}₫"

    class Meta:
        db_table = 'store_shipping_method'
        verbose_name = 'Shipping Method'
        verbose_name_plural = 'Shipping Methods'


class PaymentMethod(BaseModel):
    """Phương thức thanh toán"""
    name = models.CharField(max_length=120, null=False, blank=False, db_column='name')
    code = models.CharField(max_length=60, null=False, blank=False, unique=True, db_column='code', help_text="Mã định danh: COD, MOMO, VNPAY...")
    active = models.BooleanField(default=True, db_column='active')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'store_payment_method'
        verbose_name = 'Payment Method'
        verbose_name_plural = 'Payment Methods'


class Order(BaseModel):
    """Đơn hàng online"""
    PENDING = 'PENDING'
    CONFIRMED = 'CONFIRMED'
    SHIPPING = 'SHIPPING'
    DELIVERED = 'DELIVERED'
    CANCELLED = 'CANCELLED'
    
    STATUS_CHOICES = [
        (PENDING, 'Chờ xử lý'),
        (CONFIRMED, 'Đã xác nhận'),
        (SHIPPING, 'Đang giao hàng'),
        (DELIVERED, 'Đã giao'),
        (CANCELLED, 'Đã hủy'),
    ]

    order_number = models.CharField(max_length=30, null=False, blank=False, unique=True, db_index=True, db_column='order_number')
    user_id = models.BigIntegerField(null=True, blank=True, db_column='user_id', help_text="ID của User trong database default")
    shipping_address = models.TextField(null=False, blank=False, db_column='shipping_address')
    shipping_method = models.ForeignKey(ShippingMethod, on_delete=models.PROTECT, related_name='orders', db_column='shipping_method_id')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name='orders', db_column='payment_method_id')
    subtotal = models.FloatField(null=False, default=0, validators=[MinValueValidator(0)], db_column='subtotal', help_text="Tổng tiền sản phẩm")
    shipping_fee = models.FloatField(null=False, default=0, validators=[MinValueValidator(0)], db_column='shipping_fee', help_text="Phí vận chuyển")
    total = models.FloatField(null=False, default=0, validators=[MinValueValidator(0)], db_column='total', help_text="Tổng thanh toán")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_column='status')
    notes = models.TextField(null=True, blank=True, db_column='notes', help_text="Ghi chú của khách hàng")

    def save(self, *args, **kwargs):
        # Tự động generate order_number nếu chưa có
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_order_number():
        """Generate order number: ORD + YYYYMMDD + 4 digits"""
        # Sử dụng localtime để lấy ngày theo timezone của hệ thống (Asia/Bangkok UTC+7)
        # Đảm bảo order_number dùng ngày local, không phải UTC
        from django.utils import timezone as tz
        today = tz.localtime(tz.now())
        date_str = today.strftime('%Y%m%d')
        # Lấy số thứ tự trong ngày
        last_order = Order.objects.filter(
            order_number__startswith=f'ORD{date_str}'
        ).order_by('-order_number').first()
        
        if last_order:
            last_num = int(last_order.order_number[-4:])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f'ORD{date_str}{new_num:04d}'

    def __str__(self):
        return f"Đơn hàng {self.order_number} - {self.get_status_display()}"

    class Meta:
        db_table = 'store_order'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_date']


class OrderItem(BaseModel):
    """Chi tiết đơn hàng"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', db_column='order_id')
    medicine_unit_id = models.BigIntegerField(null=False, db_column='medicine_unit_id', help_text="ID của MedicineUnit trong database default")
    quantity = models.PositiveIntegerField(null=False, validators=[MinValueValidator(1)], db_column='quantity')
    price = models.FloatField(null=False, validators=[MinValueValidator(0)], db_column='price', help_text="Giá tại thời điểm đặt hàng (snapshot)")

    @property
    def subtotal(self):
        if self.quantity is None or self.price is None:
            return 0
        return self.quantity * self.price

    def __str__(self):
        return f"{self.order.order_number} - Sản phẩm #{self.medicine_unit_id} x{self.quantity}"

    class Meta:
        db_table = 'store_order_item'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'
        ordering = ['created_date']


class MedicineBatch(BaseModel):
    """Quản lý lô thuốc - theo dõi ngày nhập và hạn sử dụng"""
    batch_number = models.CharField(max_length=100, null=False, blank=False, unique=True, db_index=True, db_column='batch_number', help_text="Mã lô thuốc")
    medicine_unit_id = models.BigIntegerField(null=False, db_column='medicine_unit_id', help_text="ID của MedicineUnit trong database default")
    import_date = models.DateField(null=False, db_column='import_date', help_text="Ngày nhập kho")
    expiry_date = models.DateField(null=False, db_column='expiry_date', help_text="Hạn sử dụng")
    quantity = models.PositiveIntegerField(null=False, validators=[MinValueValidator(1)], db_column='quantity', help_text="Số lượng nhập")
    remaining_quantity = models.PositiveIntegerField(null=False, default=0, db_column='remaining_quantity', help_text="Số lượng còn lại")
    import_price = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)], db_column='import_price', help_text="Giá nhập kho (để tính lợi nhuận)")

    def __str__(self):
        return f"Batch {self.batch_number} - Exp: {self.expiry_date}"

    @property
    def is_expired(self):
        """Kiểm tra thuốc đã hết hạn chưa"""
        return timezone.now().date() > self.expiry_date

    @property
    def days_until_expiry(self):
        """Số ngày còn lại trước khi hết hạn"""
        delta = self.expiry_date - timezone.now().date()
        return delta.days

    @property
    def is_near_expiry(self, days_threshold=30):
        """Kiểm tra thuốc sắp hết hạn (mặc định 30 ngày)"""
        return 0 <= self.days_until_expiry <= days_threshold

    class Meta:
        db_table = 'store_medicine_batch'
        verbose_name = 'Medicine Batch'
        verbose_name_plural = 'Medicine Batches'
        ordering = ['expiry_date', 'import_date']
        indexes = [
            models.Index(fields=['medicine_unit_id', 'expiry_date']),
            models.Index(fields=['expiry_date', 'remaining_quantity']),
        ]


class Notification(BaseModel):
    """Thông báo cảnh báo thuốc sắp hết hạn hoặc đã hết hạn"""
    EXPIRY_WARNING = 'EXPIRY_WARNING'
    EXPIRY_URGENT = 'EXPIRY_URGENT'
    EXPIRED = 'EXPIRED'
    LOW_STOCK = 'LOW_STOCK'
    
    TYPE_CHOICES = [
        (EXPIRY_WARNING, 'Cảnh báo sắp hết hạn'),
        (EXPIRY_URGENT, 'Cảnh báo khẩn cấp'),
        (EXPIRED, 'Đã hết hạn'),
        (LOW_STOCK, 'Tồn kho thấp'),
    ]

    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, null=False, db_column='notification_type')
    medicine_unit_id = models.BigIntegerField(null=True, blank=True, db_column='medicine_unit_id', help_text="ID của MedicineUnit (null nếu là thông báo tổng hợp)")
    batch_id = models.BigIntegerField(null=True, blank=True, db_column='batch_id', help_text="ID của MedicineBatch nếu liên quan đến batch cụ thể")
    title = models.CharField(max_length=255, null=False, blank=False, db_column='title')
    message = models.TextField(null=False, blank=False, db_column='message')
    is_read = models.BooleanField(default=False, db_column='is_read')
    read_at = models.DateTimeField(null=True, blank=True, db_column='read_at')

    def mark_as_read(self):
        """Đánh dấu đã đọc"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def __str__(self):
        return f"{self.get_notification_type_display()}: {self.title}"

    class Meta:
        db_table = 'store_notification'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_date', 'is_read']
        indexes = [
            models.Index(fields=['is_read', '-created_date']),
            models.Index(fields=['medicine_unit_id', 'notification_type']),
        ]
