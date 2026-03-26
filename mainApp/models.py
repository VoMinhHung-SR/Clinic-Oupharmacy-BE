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
    id_province = models.CharField(max_length=10, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=50, null=False)


class CommonDistrict(models.Model):
    id_commune = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=50, null=False)
    city = models.ForeignKey(CommonCity, on_delete=models.CASCADE)


class UserAddress(models.Model):
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        'User', on_delete=models.CASCADE, related_name='addresses'
    )
    address = models.CharField(max_length=500, null=False)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    city = models.ForeignKey(CommonCity, on_delete=models.SET_NULL, null=True, blank=True)
    district = models.ForeignKey(CommonDistrict, on_delete=models.SET_NULL, null=True, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_default', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_default=True),
                name='one_default_address_per_user',
            )
        ]

    def __str__(self):
        return f"{self.user_id}: {(self.address[:50] + '...') if len(self.address) > 50 else self.address}"


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


# Phieu ke toa
class Prescribing(BaseModel):
    diagnosis = models.ForeignKey(Diagnosis, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)


class PrescriptionDetail(BaseModel):
    quantity = models.IntegerField(null=False)
    uses = models.CharField(max_length=100, null=False)

    prescribing = models.ForeignKey(Prescribing, on_delete=models.CASCADE)
    # Transitional soft references to storeApp entities (cross-DB safe, no FK constraint).
    product_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    product_variant_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    product_variant_unit_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    item_name_snapshot = models.CharField(max_length=500, null=True, blank=True)
    unit_name_snapshot = models.CharField(max_length=100, null=True, blank=True)
    unit_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quantity_in_base_snapshot = models.PositiveIntegerField(default=1)


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



