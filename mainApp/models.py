import pytz
import datetime

from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.utils import timezone
from cloudinary.models import CloudinaryField
# Create your models here.
ADMIN_ROLE = "ADMIN"


class BaseModel(models.Model):
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        tz = pytz.timezone('Asia/Bangkok')  # specify the timezone as UTC+7
        if not self.id:
            self.created_date = datetime.datetime.now(tz)
        self.updated_date = datetime.datetime.now(tz)
        super(BaseModel, self).save(*args, **kwargs)


class CommonCity(models.Model):
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=50, null=False)


class CommonDistrict(models.Model):
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=50, null=False)
    city = models.ForeignKey(CommonCity, on_delete=models.CASCADE)


class CommonLocation(models.Model):
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    address = models.CharField(max_length=255, null=False)
    lat = models.FloatField(null=False)
    lng = models.FloatField(null=False)
    city = models.ForeignKey(CommonCity, on_delete=models.SET_NULL, null=True)
    district = models.ForeignKey(CommonDistrict, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.address


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_admin', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class UserRole(models.Model):
    # "Keep follow this format" (UPPERCASE-ALL + PREFIX:ROLE_")
    # ex: (1:ROLE_USER; 2:ROLE_DOCTOR; 3:ROLE_NURSE)
    name = models.CharField(max_length=50, null=False, unique=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    # 0, 1, 2
    male, female, secret = range(3)
    genders = [(male, 'Male'), (female, 'Female'), (secret, 'Secret')]
    username = None
    email = models.EmailField(max_length=100, null=False, blank=False, unique=True, db_index=True)

    avatar = CloudinaryField('avatar', folder='OUPharmacy/users/avatar', default='', blank=True, null=True)
    phone_number = models.CharField(max_length=20, null=False, blank=True)
    date_of_birth = models.DateTimeField(null=True)
    gender = models.PositiveIntegerField(choices=genders, default=male)
    title = models.CharField(max_length=20, null=True, blank=True, default='')
    # Keep follow this format (UPPERCASE-ALL + PREFIX:ROLE_")
    # ex: (1:ROLE_USER; 2:ROLE_DOCTOR; 3:ROLE_NURSE)
    role = models.ForeignKey(UserRole, on_delete=models.SET_NULL, null=True)
    location = models.ForeignKey(CommonLocation, on_delete=models.SET_NULL, null=True)
    objects = UserManager()
    is_admin = models.BooleanField(default=False)
    # Social Authentication fields
    social_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    social_provider = models.CharField(max_length=50, blank=True, null=True)  # 'google', 'facebook'
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def __str__(self):
        return f"{self.title} {self.first_name} {self.last_name} ({self.email})"

class SpecializationTag(BaseModel):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')
    description = models.TextField(blank=True, null=True)
    specializations = models.ManyToManyField(SpecializationTag, related_name='doctors')

    def __str__(self):
        return f"Dr. {self.user.get_full_name()}"

class Patient(BaseModel):
    # 0 , 1, 2
    male, female, secret = range(3)
    genders = [(male, 'Male'), (female, 'Female'), (secret, 'Secret')]

    first_name = models.CharField(max_length=150, null=False, blank=True)
    last_name = models.CharField(max_length=150, null=False, blank=True)
    phone_number = models.CharField(max_length=20)
    email = models.CharField(max_length=254, null=False, unique=True)
    gender = models.PositiveIntegerField(choices=genders, default=male)
    date_of_birth = models.DateTimeField(null=True)
    address = models.CharField(max_length=255, null=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return self.first_name + ' ' + self.last_name

class DoctorSchedule(models.Model):
    doctor = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    session = models.CharField(
        choices=[('morning', 'morning'), ('afternoon', 'afternoon')],
        max_length=10
    )
    is_off = models.BooleanField(default=False)
    def __str__(self):
        return f"{self.doctor.title} {self.doctor} - {self.date} ({self.get_session_display()})"

class TimeSlot(models.Model):
    schedule = models.ForeignKey(DoctorSchedule, on_delete=models.CASCADE)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.schedule} ({self.start_time} - {self.end_time})"

class Examination(BaseModel):

    class Meta:
        # id (3...2...1)
        ordering = ["-id"]
    wage = models.FloatField(null=False, default=20000)
    mail_status = models.BooleanField(null=True, default=False)
    reminder_email = models.BooleanField(null=True, default=False)
    description = models.CharField(max_length=254, null=False, blank=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=False)
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, null=True)
    def __str__(self):
        return f"{self.patient} - {self.time_slot}"

# Phieu chuan doan
class Diagnosis(BaseModel):
    sign = models.CharField(max_length=254, null=False, blank=False)
    diagnosed = models.CharField(max_length=254, null=False, blank=False)
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, blank=False, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.sign

    class Meta:
        verbose_name_plural = "Diagnosis"


class Medicine(BaseModel):
    """Medicine model"""
    # basicInfo
    name = models.CharField(max_length=254, null=False, blank=False, unique=True, db_index=True, help_text="basicInfo.name")
    mid = models.CharField(max_length=64, null=True, blank=True, unique=True, db_index=True, help_text="basicInfo.mid - Mã định danh sản phẩm (MID)")
    slug = models.CharField(max_length=300, null=True, blank=True, unique=True, db_index=True, help_text="basicInfo.slug - URL slug")
    web_name = models.CharField(max_length=500, null=True, blank=True, help_text="basicInfo.webName - Tên hiển thị trên web")
    
    # content
    description = models.TextField(null=True, blank=True, help_text="content.description - Mô tả sản phẩm")
    ingredients = models.TextField(null=True, blank=True, help_text="content.ingredients - Thành phần")
    usage = models.TextField(null=True, blank=True, help_text="content.usage - Cách sử dụng/Công dụng")
    dosage = models.TextField(null=True, blank=True, help_text="content.dosage - Liều dùng")
    adverse_effect = models.TextField(null=True, blank=True, help_text="content.adverseEffect - Tác dụng phụ")
    careful = models.TextField(null=True, blank=True, help_text="content.careful - Lưu ý/Cảnh báo")
    preservation = models.TextField(null=True, blank=True, help_text="content.preservation - Bảo quản")
    
    # Foreign Keys
    brand_id = models.BigIntegerField(null=True, blank=True, db_index=True, help_text="basicInfo.brand - ID của Brand trong store database")

    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=['mid']),
            models.Index(fields=['slug']),
            models.Index(fields=['brand_id']),
            models.Index(fields=['name']),  # For search
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
        """
        Tạo/get nested categories từ array format: [{"name":"...","slug":"..."}, ...]
        Trả về category cuối cùng (leaf category)
        
        Args:
            category_array: List of dicts [{"name":"...","slug":"..."}, ...]
            cache: Optional dict để cache categories (tối ưu cho bulk import)
        """
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
            
            # Cache key: (parent_id, slug)
            cache_key = (parent.id if parent else None, slug)
            
            if cache_key in cache:
                parent = cache[cache_key]
            else:
                # Get or create category
                category, created = cls.objects.get_or_create(
                    slug=slug,
                    parent=parent,
                    defaults={'name': name}
                )
                cache[cache_key] = category
                parent = category
        
        return parent

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['level', 'name']
        unique_together = [['parent', 'slug']]  # Slug unique per parent
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['parent', 'level']),
            models.Index(fields=['path_slug']),
        ]


class MedicineUnit(BaseModel):
    in_stock = models.IntegerField(null=False, default=0, db_index=True, help_text="Số lượng tồn kho")
    
    # pricing
    price_display = models.CharField(max_length=50, null=True, blank=True, help_text="pricing.priceDisplay - Giá hiển thị: 567.000đ")
    price_value = models.FloatField(null=False, default=0, db_index=True, help_text="pricing.priceValue - Giá trị số (dùng để filter/sort)")
    original_price = models.CharField(max_length=50, null=True, blank=True, help_text="pricing.originalPrice - Giá gốc (string)")
    original_price_value = models.FloatField(null=True, blank=True, db_index=True, help_text="pricing.originalPriceValue - Giá trị số của giá gốc")
    package_size = models.CharField(max_length=100, null=True, blank=True, help_text="pricing.packageSize - Quy cách đóng gói")
    package_options = models.JSONField(default=list, blank=True, help_text="pricing.packageOptions - Danh sách các tùy chọn đóng gói (JSON array)")
    prices = models.JSONField(default=list, blank=True, help_text="pricing.prices - Danh sách giá (JSON array)")
    price_obj = models.JSONField(default=dict, null=True, blank=True, help_text="pricing.priceObj - Object giá (JSON object)")
    
    # media
    image = CloudinaryField('medicines', default='', null=True, folder='OUPharmacy/medicines/image', help_text="media.image - Ảnh chính")
    images = models.JSONField(default=list, blank=True, help_text="media.images - Danh sách ảnh gallery (JSON array)")
    
    # Rating & Reviews - TODO: Implement later
    # rating = models.FloatField(null=True, blank=True, db_index=True, help_text="rating.rating - Đánh giá trung bình (float)")
    # review_count = models.IntegerField(default=0, db_index=True, help_text="rating.reviewCount - Số lượng đánh giá (integer)")
    # comment_count = models.IntegerField(default=0, help_text="rating.commentCount - Số lượng bình luận (integer)")
    # reviews = models.TextField(null=True, blank=True, help_text="rating.reviews - Đánh giá chi tiết")
    
    # specifications
    registration_number = models.CharField(max_length=100, null=True, blank=True, help_text="specifications.registrationNumber - Số đăng ký")
    origin = models.CharField(max_length=200, null=True, blank=True, help_text="specifications.origin - Xuất xứ")
    manufacturer = models.TextField(null=True, blank=True, help_text="specifications.manufacturer - Nhà sản xuất (TextField để lưu trữ đầy đủ)")
    shelf_life = models.CharField(max_length=100, null=True, blank=True, help_text="specifications.shelfLife - Hạn sử dụng")
    specifications = models.JSONField(default=dict, null=True, blank=True, help_text="specifications.specifications - Object specification (JSON object)")
    
    # metadata
    link = models.URLField(max_length=500, null=True, blank=True, help_text="metadata.link - Link sản phẩm")
    product_ranking = models.IntegerField(default=0, db_index=True, help_text="metadata.productRanking - Product ranking")
    display_code = models.IntegerField(null=True, blank=True, help_text="metadata.displayCode - Display code")
    is_published = models.BooleanField(default=True, db_index=True, help_text="metadata.isPublish - Published status")
    is_hot = models.BooleanField(default=False, db_index=True, help_text="Sản phẩm hot/nổi bật")
    
    # Foreign Keys
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='units', db_index=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, db_index=True, help_text="category - Category cuối cùng (leaf) trong hierarchy")
    
    def get_category_info(self):
        if not self.category:
            return {
                'category': [],
                'categoryPath': '',
                'categorySlug': ''
            }
        
        return {
            'category': self.category.get_category_array(),
            'categoryPath': self.category.path or '',
            'categorySlug': self.category.path_slug or ''
        }
    
    class Meta:
        indexes = [
            models.Index(fields=['is_published', 'product_ranking']),
            models.Index(fields=['category', 'is_published']),
            models.Index(fields=['price_value', 'is_published']),  # For price filtering
            models.Index(fields=['medicine', 'is_published']),  # For medicine filtering
            models.Index(fields=['original_price_value', 'is_published']),  # For original price filtering
            models.Index(fields=['is_hot', 'is_published']),  # For hot products filtering
        ]

class MedicineUnitStats(models.Model):
    unit = models.OneToOneField(
        MedicineUnit,
        on_delete=models.CASCADE,
        related_name='stats'
    )

    sold_total = models.IntegerField(default=0, db_index=True)
    sold_30d = models.IntegerField(default=0, db_index=True)
    sold_7d = models.IntegerField(default=0, db_index=True)

    view_count = models.IntegerField(default=0, db_index=True)
    wishlist_count = models.IntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)


# Phieu ke toa
class Prescribing(BaseModel):
    diagnosis = models.ForeignKey(Diagnosis, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)


class PrescriptionDetail(BaseModel):
    quantity = models.IntegerField(null=False)
    uses = models.CharField(max_length=100, null=False)

    prescribing = models.ForeignKey(Prescribing, on_delete=models.CASCADE)
    medicine_unit = models.ForeignKey(MedicineUnit, on_delete=models.SET_NULL, null=True)


class Bill(BaseModel):

    amount = models.FloatField(null=False)
    prescribing = models.ForeignKey(Prescribing, on_delete=models.SET_NULL, null=True)


class Voucher(BaseModel):
    """Model quản lý voucher/giảm giá - Reference tới Product bằng ID/MID/Category"""
    
    # Voucher identification
    code = models.CharField(max_length=50, null=False, blank=False, unique=True, db_index=True, help_text="Mã voucher (ví dụ: NEWUSER50)")
    
    # Discount type & value
    type = models.CharField(max_length=10, choices=[('FIXED', 'Fixed Amount'), ('PERCENT', 'Percentage')], default='PERCENT', help_text="Loại giảm giá: FIXED (số tiền cố định) hoặc PERCENT (phần trăm)")
    value = models.FloatField(null=False, default=0, help_text="Giá trị giảm giá (số tiền nếu FIXED, phần trăm nếu PERCENT)")
    max_discount = models.FloatField(null=True, blank=True, help_text="Giảm giá tối đa (chỉ áp dụng cho PERCENT type)")
    min_order_value = models.FloatField(null=True, blank=True, default=0, help_text="Giá trị đơn hàng tối thiểu để áp dụng voucher")
    
    # Applicability
    applicable_products = models.JSONField(default=list, blank=True, help_text="Danh sách MID sản phẩm áp dụng (empty = áp dụng tất cả)")
    applicable_categories = models.JSONField(default=list, blank=True, help_text="Danh sách category slug áp dụng (empty = áp dụng tất cả)")
    
    # Time management
    start_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Ngày bắt đầu áp dụng voucher (null = áp dụng ngay)")
    end_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Ngày kết thúc voucher (null = không giới hạn)")
    
    # Usage limits
    usage_limit = models.IntegerField(null=True, blank=True, help_text="Số lần sử dụng tối đa (null = không giới hạn)")
    used_count = models.IntegerField(default=0, db_index=True, help_text="Số lần đã sử dụng voucher")
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True, help_text="Trạng thái active của voucher")
    description = models.CharField(max_length=255, null=True, blank=True, help_text="Mô tả chương trình giảm giá")
    
    def is_valid(self):
        """Kiểm tra voucher còn hiệu lực không"""
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
    
    def is_applicable(self, product_mid=None, category_slug=None, order_value=0):
        """Kiểm tra voucher có áp dụng được cho sản phẩm/đơn hàng không"""
        if not self.is_valid():
            return False
        
        # Check min order value
        if self.min_order_value and order_value < self.min_order_value:
            return False
        
        # Check applicable products
        if self.applicable_products:
            if not product_mid or product_mid not in self.applicable_products:
                return False
        
        # Check applicable categories
        if self.applicable_categories:
            if not category_slug or category_slug not in self.applicable_categories:
                return False
        
        return True
    
    def calculate_discount(self, original_price):
        """Tính số tiền giảm giá"""
        if self.type == 'PERCENT':
            discount = original_price * (self.value / 100)
            if self.max_discount:
                discount = min(discount, self.max_discount)
            return discount
        else:  # FIXED
            return min(self.value, original_price)
    
    def apply_voucher(self, order_value):
        """Áp dụng voucher và tăng used_count"""
        if self.is_valid():
            self.used_count += 1
            self.save(update_fields=['used_count'])
            return self.calculate_discount(order_value)
        return 0
    
    def __str__(self):
        if self.type == 'PERCENT':
            return f"{self.code} - {self.value}% off"
        return f"{self.code} - {self.value:,.0f}₫ off"
    
    class Meta:
        ordering = ['-created_date']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active', 'start_at', 'end_at']),
            models.Index(fields=['used_count', 'usage_limit']),
        ]



