from django.db import models
from django.db import IntegrityError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.core.validators import MinValueValidator
from cloudinary.models import CloudinaryField
from mainApp.models import BaseModel
from decimal import Decimal, InvalidOperation
import unicodedata


class Brand(BaseModel):
    """Thương hiệu sản phẩm"""
    name = models.CharField(max_length=120, null=False, blank=False, unique=True, db_column='name')
    country = models.CharField(max_length=100, null=True, blank=True, db_column='country', help_text="Quốc gia sản phẩm")
    active = models.BooleanField(default=True, db_column='active')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'store_brand'
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'
        indexes = [
            models.Index(fields=['country', 'active']), 
        ]


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
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, null=False, default=0,
        validators=[MinValueValidator(0)], db_column='subtotal', help_text="Tổng tiền sản phẩm",
    )
    shipping_fee = models.DecimalField(
        max_digits=12, decimal_places=2, null=False, default=0,
        validators=[MinValueValidator(0)], db_column='shipping_fee', help_text="Phí vận chuyển",
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, null=False, default=0,
        validators=[MinValueValidator(0)], db_column='total', help_text="Tổng thanh toán",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_column='status')
    notes = models.TextField(null=True, blank=True, db_column='notes', help_text="Ghi chú của khách hàng")

    def save(self, *args, **kwargs):
        # Generate order_number với retry để giảm rủi ro race condition.
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
    product_variant = models.ForeignKey('ProductVariant', on_delete=models.PROTECT, related_name='order_items', db_column='product_variant_id')
    product_variant_unit = models.ForeignKey(
        'ProductVariantUnit',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='order_items',
        db_column='product_variant_unit_id',
        help_text="Đơn vị bán đã chọn (Hộp/Lọ/...); null = dữ liệu cũ hoặc mặc định theo variant",
    )
    quantity = models.PositiveIntegerField(null=False, validators=[MinValueValidator(1)], db_column='quantity')
    price = models.DecimalField(
        max_digits=12, decimal_places=2, null=False,
        validators=[MinValueValidator(0)], db_column='price',
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
        db_table = 'store_order_item'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'
        ordering = ['created_date']


class MedicineBatch(BaseModel):
    """Quản lý lô thuốc - theo dõi ngày nhập và hạn sử dụng"""
    batch_number = models.CharField(max_length=100, null=False, blank=False, unique=True, db_index=True, db_column='batch_number', help_text="Mã lô thuốc")
    product_variant = models.ForeignKey('ProductVariant', on_delete=models.PROTECT, related_name='batches', db_column='product_variant_id')
    
    import_date = models.DateField(null=False, db_column='import_date', help_text="Ngày nhập kho")
    expiry_date = models.DateField(null=False, db_column='expiry_date', help_text="Hạn sử dụng")
    
    quantity = models.PositiveIntegerField(null=False, validators=[MinValueValidator(1)], db_column='quantity', help_text="Số lượng nhập theo đơn vị cơ sở")
    remaining_quantity = models.PositiveIntegerField(null=False, default=0, db_column='remaining_quantity', help_text="Số lượng còn lại theo đơn vị cơ sở")
    import_price_per_base_unit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    
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
    def is_near_expiry(self):
        """Thuốc sắp hết hạn theo ngưỡng mặc định 30 ngày."""
        return self.is_near_expiry_within(30)

    def is_near_expiry_within(self, days_threshold=30):
        """Kiểm tra thuốc sắp hết hạn với ngưỡng ngày tùy chỉnh."""
        return 0 <= self.days_until_expiry <= days_threshold

    class Meta:
        db_table = 'store_medicine_batch'
        verbose_name = 'Medicine Batch'
        verbose_name_plural = 'Medicine Batches'
        ordering = ['expiry_date', 'import_date']
        indexes = [
            models.Index(fields=['product_variant', 'expiry_date']),
            models.Index(fields=['expiry_date', 'remaining_quantity']),
        ]


class Notification(BaseModel):
    """Thông báo cảnh báo thuốc sắp hết hạn hoặc đã hết hạn"""
    EXPIRY_WARNING = 'EXPIRY_WARNING'
    EXPIRY_URGENT = 'EXPIRY_URGENT'
    EXPIRED = 'EXPIRED'
    LOW_STOCK = 'LOW_STOCK'
    ADMIN_SUPPORT = 'ADMIN_SUPPORT'
    OTHERS = 'OTHERS'
    
    TYPE_CHOICES = [
        (EXPIRY_WARNING, 'Cảnh báo sắp hết hạn'),
        (EXPIRY_URGENT, 'Cảnh báo khẩn cấp'),
        (EXPIRED, 'Đã hết hạn'),
        (LOW_STOCK, 'Tồn kho thấp'),
        (ADMIN_SUPPORT, 'Liên hệ hỗ trợ'),
        (OTHERS, 'Khác'),
    ]

    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, null=False, db_column='notification_type')
    product_variant = models.ForeignKey('ProductVariant', on_delete=models.CASCADE, related_name='notifications', db_column='product_variant_id', null=True, blank=True)
    batch = models.ForeignKey('MedicineBatch', on_delete=models.CASCADE, related_name='notifications', db_column='batch_id', null=True, blank=True)
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
            models.Index(fields=['product_variant', 'notification_type']),
        ]


class SearchKeyword(BaseModel):
    """Từ khóa tìm kiếm — theo dõi lượt tìm để hiển thị 'Tìm kiếm phổ biến' (vd: Omega 3, Canxi)."""
    keyword = models.CharField(max_length=120, null=False, blank=False, db_index=True, db_column='keyword')
    keyword_lookup = models.CharField(max_length=120, null=False, blank=False, unique=True, db_index=True, db_column='keyword_lookup')
    hit_count = models.PositiveIntegerField(default=1, db_column='hit_count', help_text='Số lần người dùng tìm với từ khóa này')
    last_searched_at = models.DateTimeField(auto_now=True, db_column='last_searched_at')

    @staticmethod
    def normalize_keyword(keyword: str) -> str:
        if not keyword:
            return ""
        # Chuẩn hóa unicode + gộp khoảng trắng để giữ format hiển thị ổn định.
        normalized = unicodedata.normalize("NFKC", keyword)
        return " ".join(normalized.strip().split())

    @classmethod
    def record_search(cls, keyword: str):
        normalized_display = cls.normalize_keyword(keyword)
        normalized_lookup = normalized_display.casefold()
        if not normalized_lookup:
            raise ValueError("keyword must not be empty after normalization")

        with transaction.atomic():
            obj = cls.objects.filter(keyword_lookup=normalized_lookup).first()
            if obj:
                obj.hit_count = F("hit_count") + 1
                obj.save(update_fields=["hit_count", "last_searched_at"])
                obj.refresh_from_db(fields=["hit_count", "last_searched_at"])
                return obj
            try:
                return cls.objects.create(
                    keyword=normalized_display,
                    keyword_lookup=normalized_lookup,
                    hit_count=1,
                )
            except IntegrityError:
                # Concurrent request có thể vừa tạo cùng keyword (case-insensitive) trước đó.
                
                obj = cls.objects.filter(keyword_lookup=normalized_lookup).first()
                if obj:
                    obj.hit_count = F("hit_count") + 1
                    obj.save(update_fields=["hit_count", "last_searched_at"])
                    obj.refresh_from_db(fields=["hit_count", "last_searched_at"])
                    return obj
                raise

    def save(self, *args, **kwargs):
        self.keyword = self.normalize_keyword(self.keyword)
        self.keyword_lookup = self.keyword.casefold()
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'store_search_keyword'
        verbose_name = 'Search Keyword'
        verbose_name_plural = 'Search Keywords'
        ordering = ['-hit_count', '-last_searched_at']
        indexes = [
            models.Index(fields=['-hit_count']),
        ]


class Category(BaseModel):
    name = models.CharField(max_length=254, null=False, blank=False)
    slug = models.CharField(max_length=254, null=True, blank=True, db_index=True, help_text="URL slug cho category (unique per parent) - auto-generated")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    level = models.PositiveIntegerField(default=0, help_text="Level trong hierarchy (0 = root)")
    path = models.CharField(max_length=500, null=True, blank=True, help_text="category.categoryPath")
    path_slug = models.CharField(max_length=500, null=True, blank=True, unique=True, db_index=True, help_text="category.categorySlug (unique)")

    def __str__(self):
        return self.path if self.path else self.name

    def _generate_slug_from_name(self):
        """Generate slug từ name nếu chưa có"""
        if not self.slug and self.name:
            import re
            from django.utils.text import slugify
            slug = slugify(self.name)
            if not slug:
                slug = self.name.lower()
                slug = re.sub(r'[^\w\s-]', '', slug)
                slug = re.sub(r'[-\s]+', '-', slug)
            self.slug = slug[:254]
        return self.slug

    def save(self, *args, **kwargs):
        """Auto-calculate level, path, và path_slug khi save"""
        old_path_slug = None
        hierarchy_changed = False
        if self.pk:
            previous = Category.objects.filter(pk=self.pk).values("name", "slug", "parent_id", "path_slug").first()
            if previous:
                old_path_slug = previous["path_slug"]
                hierarchy_changed = (
                    previous["name"] != self.name
                    or previous["slug"] != self.slug
                    or previous["parent_id"] != self.parent_id
                )

        self._generate_slug_from_name()
        
        if self.parent:
            self.level = self.parent.level + 1
            self.path = f"{self.parent.path} > {self.name}" if self.parent.path else f"{self.parent.name} > {self.name}"
            self.path_slug = f"{self.parent.path_slug}/{self.slug}" if self.parent.path_slug else f"{self.parent.slug}/{self.slug}"
        else:
            self.level = 0
            self.path = self.name
            self.path_slug = self.slug
        super().save(*args, **kwargs)

        if hierarchy_changed and old_path_slug and old_path_slug != self.path_slug:
            self._refresh_descendant_paths(old_path_slug)

    def _refresh_descendant_paths(self, old_path_slug):
        """Cập nhật path/path_slug/level cho toàn bộ category con khi node cha đổi."""
        prefix = f"{old_path_slug}/"
        descendants = (
            Category.objects
            .select_related("parent")
            .filter(path_slug__startswith=prefix)
            .exclude(pk=self.pk)
            .order_by("level", "id")
        )
        for node in descendants:
            parent = node.parent
            if not parent:
                continue
            new_level = parent.level + 1
            new_path = f"{parent.path} > {node.name}" if parent.path else f"{parent.name} > {node.name}"
            new_path_slug = f"{parent.path_slug}/{node.slug}" if parent.path_slug else node.slug
            Category.objects.filter(pk=node.pk).update(
                level=new_level,
                path=new_path,
                path_slug=new_path_slug,
            )

    def get_category_array(self):
        """Trả về category array format theo schema: [{"name":"...","slug":"..."}, ...]"""
        categories = []
        current = self
        path = []
        
        # Build path từ leaf lên root
        while current:
            path.insert(0, {'name': current.name, 'slug': current.slug})
            current = current.parent
        
        return path

    @classmethod
    def get_or_create_from_array(cls, category_array, cache=None):
        if not category_array or not isinstance(category_array, list):
            return None
        
        if cache is None:
            cache = {}
        
        parent = None
        for cat_data in category_array:
            if not isinstance(cat_data, dict):
                continue
            
            name = cat_data.get('name', '').strip()
            slug = cat_data.get('slug', '').strip()
            
            if not name or not slug:
                continue
            
            cache_key = (parent.id if parent else None, slug)
            
            if cache_key in cache:
                parent = cache[cache_key]
            else:
                category, created = cls.objects.get_or_create(
                    slug=slug,
                    parent=parent,
                    defaults={'name': name}
                )
                cache[cache_key] = category
                parent = category
        
        return parent

    class Meta:
        db_table = 'store_category'
        verbose_name = 'Category'
        verbose_name_plural = "Categories"
        ordering = ['level', 'name']
        unique_together = [['parent', 'slug']]
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['parent', 'level']),
            models.Index(fields=['path_slug']),
        ]


class Product(BaseModel):
    """Product model (migrated from Medicine)"""
    name = models.CharField(max_length=254, null=False, blank=False, unique=True, db_index=True)
    mid = models.CharField(max_length=64, null=True, blank=True, unique=True, db_index=True)
    slug = models.CharField(max_length=300, null=True, blank=True, unique=True, db_index=True)
    web_name = models.CharField(max_length=500, null=True, blank=True)
    
    description = models.TextField(null=True, blank=True)
    ingredients = models.TextField(null=True, blank=True)
    usage = models.TextField(null=True, blank=True)
    dosage = models.TextField(null=True, blank=True)
    adverse_effect = models.TextField(null=True, blank=True)
    careful = models.TextField(null=True, blank=True)
    preservation = models.TextField(null=True, blank=True)
    
    origin = models.CharField(max_length=200, null=True, blank=True)
    manufacturer = models.TextField(null=True, blank=True)
    shelf_life = models.CharField(max_length=100, null=True, blank=True)
    specifications = models.JSONField(default=dict, null=True, blank=True)
    
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'store_product'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        indexes = [
            models.Index(fields=['mid']),
            models.Index(fields=['slug']),
            models.Index(fields=['name']),
        ]


class ProductVariant(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants', db_index=True)
    sku = models.CharField(max_length=100, null=True, blank=True, unique=True, db_index=True, help_text="Stock Keeping Unit")

    packing = models.CharField(max_length=100, null=True, blank=True, help_text="Quy cách đóng gói, ví dụ: Hộp 30 viên")
    packing_meta = models.JSONField(default=dict, blank=True)
    
    image = CloudinaryField('products', default='', null=True, folder='OUPharmacy/products/image')
    images = models.JSONField(default=list, blank=True)

    registration_number = models.CharField(max_length=100, null=True, blank=True)
    base_unit = models.CharField(max_length=50, null=True, blank=True, db_index=True, help_text="Đơn vị cơ sở nhỏ nhất, ví dụ: viên, gói")
    
    in_stock = models.IntegerField(null=False, default=0, db_index=True, help_text="Tồn kho cache theo đơn vị cơ sở (base unit)")
    product_ranking = models.IntegerField(default=0, db_index=True)
    
    is_published = models.BooleanField(default=True, db_index=True)
    is_hot = models.BooleanField(default=False, db_index=True)
 
    def __str__(self):
        return f"{self.product.name} - {self.packing}"

    def get_category_info(self):
        cat = self.product.category
        if not cat:
            return {'category': [], 'categoryPath': '', 'categorySlug': ''}
        return {
            'category': cat.get_category_array(),
            'categoryPath': cat.path or '',
            'categorySlug': cat.path_slug or ''
        }

    class Meta:
        db_table = 'store_product_variant'
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
        indexes = [
            models.Index(fields=['is_published', 'product_ranking']),
            models.Index(fields=['is_hot', 'is_published']),
        ]

class ProductVariantUnit(BaseModel):
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='units', db_column='product_variant_id')
    quantity_in_base = models.PositiveIntegerField(default=1, help_text="1 Hộp = 30 viên, 1 Vỉ = 10 viên")
    
    unit_name = models.CharField(max_length=50, db_index=True, help_text="Hộp, Vỉ, Viên, Gói...")
    unit_order = models.PositiveIntegerField(default=0)
    
    price_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    price_display = models.CharField(max_length=50, null=True, blank=True)

    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_default = models.BooleanField(default=False, db_index=True)
    is_published = models.BooleanField(default=True, db_index=True)

    def save(self, *args, **kwargs):
        using = kwargs.get('using') or getattr(self._state, 'db', None)
        super().save(*args, **kwargs)
        if self.is_default and self.variant_id:
            db = using or getattr(self._state, 'db', None) or 'default'
            type(self).objects.using(db).filter(variant_id=self.variant_id).exclude(pk=self.pk).update(
                is_default=False
            )

    class Meta:
        unique_together = [('variant', 'unit_name')]
        ordering = ['unit_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['variant'],
                condition=models.Q(is_default=True),
                name='store_pvu_one_default_per_variant',
            ),
            models.CheckConstraint(
                check=models.Q(quantity_in_base__gte=1),
                name='store_pvu_quantity_in_base_gte_1',
            ),
        ]

class ProductVariantStats(models.Model):
    variant = models.OneToOneField(ProductVariant, on_delete=models.CASCADE, related_name='stats')
    sold_total = models.IntegerField(default=0, db_index=True)
    sold_30d = models.IntegerField(default=0, db_index=True)
    sold_7d = models.IntegerField(default=0, db_index=True)
    view_count = models.IntegerField(default=0, db_index=True)
    wishlist_count = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_product_variant_stats'
        verbose_name = 'Product Variant Stats'
        verbose_name_plural = 'Product Variant Stats'


class Voucher(BaseModel):
    """Model quản lý voucher/giảm giá"""
    
    code = models.CharField(max_length=50, null=False, blank=False, unique=True, db_index=True)
    type = models.CharField(max_length=10, choices=[('FIXED', 'Fixed Amount'), ('PERCENT', 'Percentage')], default='PERCENT')
    value = models.DecimalField(max_digits=12, decimal_places=2, null=False, default=0)
    max_discount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_order_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    
    applicable_products = models.JSONField(default=list, blank=True)
    applicable_categories = models.JSONField(default=list, blank=True)
    
    start_at = models.DateTimeField(null=True, blank=True, db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)
    usage_limit = models.IntegerField(null=True, blank=True)
    used_count = models.IntegerField(default=0, db_index=True)
    
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.CharField(max_length=255, null=True, blank=True)

    @staticmethod
    def _to_decimal(value, default='0'):
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
        items_qs = order.items.select_related("product_variant__product__category").all()
        for item in items_qs:
            product = getattr(getattr(item, "product_variant", None), "product", None)
            if not product:
                continue
            if product.mid:
                product_mids.add(product.mid)
            category = getattr(product, "category", None)
            if category and category.slug:
                category_slugs.add(category.slug)
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

    def is_applicable(self, order):
        if not self.is_valid():
            return False

        if order is None:
            return False

        order_value = self._to_decimal(getattr(order, "subtotal", None))
        min_order_value = self._to_decimal(self.min_order_value)
        if min_order_value and order_value < min_order_value:
            return False

        product_mids, category_slugs = self._extract_order_item_context(order)

        if self.applicable_products:
            applicable_products = {str(mid) for mid in self.applicable_products}
            if not product_mids.intersection(applicable_products):
                return False

        if self.applicable_categories:
            applicable_categories = {str(slug) for slug in self.applicable_categories}
            if not category_slugs.intersection(applicable_categories):
                return False

        return True

    def calculate_discount(self, original_price):
        order_amount = self._to_decimal(original_price)
        if order_amount <= Decimal('0'):
            return Decimal('0')

        if self.type == 'PERCENT':
            voucher_value = self._to_decimal(self.value)
            discount = order_amount * (voucher_value / Decimal('100'))
            if self.max_discount is not None:
                discount = min(discount, self._to_decimal(self.max_discount))
            return max(Decimal('0'), discount)

        fixed_discount = self._to_decimal(self.value)
        return max(Decimal('0'), min(fixed_discount, order_amount))

    def apply_voucher(self, order):
        if not self.is_applicable(order):
            return Decimal('0')

        order_value = self._to_decimal(getattr(order, "subtotal", None))
        return self.calculate_discount(order_value)

    def increment_used_count(self):
        with transaction.atomic():
            locked_voucher = Voucher.objects.select_for_update().get(pk=self.pk)
            if not locked_voucher.is_valid():
                return False
            locked_voucher.used_count += 1
            locked_voucher.save(update_fields=['used_count'])
            self.used_count = locked_voucher.used_count
            return True
    
    def __str__(self):
        if self.type == 'PERCENT':
            return f"{self.code} - {self.value}% off"
        return f"{self.code} - {self.value:,.0f}₫ off"
    
    class Meta:
        db_table = 'store_voucher'
        verbose_name = 'Voucher'
        verbose_name_plural = 'Vouchers'
        ordering = ['-created_date']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active', 'start_at', 'end_at']),
            models.Index(fields=['used_count', 'usage_limit']),
        ]
