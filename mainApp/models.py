import pytz
import datetime

from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.contrib.auth.models import AbstractUser, Group
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
    # Business admin: Clinic FE ops + Jazzmin Campaign (D-18). Full Jazzmin remains is_superuser.
    is_admin = models.BooleanField(default=False)
    # Social Authentication fields
    social_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    social_provider = models.CharField(max_length=50, blank=True, null=True)  # 'google', 'facebook'
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def has_perm(self, perm, obj=None):
        """Django perms for Jazzmin. Business dashboard uses is_admin, not this hook."""
        if not self.is_active:
            return False
        if self.is_superuser:
            return True
        return super().has_perm(perm, obj)

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
    allergies = models.TextField(blank=True, default="")

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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "start_time", "end_time"],
                name="uniq_timeslot_schedule_start_end",
            ),
        ]

    def __str__(self):
        return f"{self.schedule} ({self.start_time} - {self.end_time})"

class Examination(BaseModel):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_NO_SHOW = "no_show"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_CONFIRMED, "confirmed"),
        (STATUS_IN_PROGRESS, "in_progress"),
        (STATUS_COMPLETED, "completed"),
        (STATUS_CANCELLED, "cancelled"),
        (STATUS_NO_SHOW, "no_show"),
    ]

    class Meta:
        # id (3...2...1)
        ordering = ["-id"]

    wage = models.FloatField(null=False, default=20000)
    mail_status = models.BooleanField(null=True, default=False)
    reminder_email = models.BooleanField(null=True, default=False)
    description = models.CharField(max_length=254, blank=True, null=False, default="")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=["examination"],
                condition=models.Q(active=True),
                name="uniq_active_diagnosis_per_examination",
            ),
        ]


# Phieu ke toa
class Prescribing(BaseModel):
    diagnosis = models.ForeignKey(Diagnosis, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["diagnosis"],
                condition=models.Q(active=True),
                name="uniq_active_prescribing_per_diagnosis",
            ),
        ]


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
    STATUS_UNPAID = "unpaid"
    STATUS_PAID = "paid"
    STATUS_VOID = "void"
    STATUS_CHOICES = [
        (STATUS_UNPAID, "unpaid"),
        (STATUS_PAID, "paid"),
        (STATUS_VOID, "void"),
    ]

    amount = models.FloatField(null=False)
    prescribing = models.ForeignKey(Prescribing, on_delete=models.SET_NULL, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UNPAID,
        db_index=True,
    )
    paid_at = models.DateTimeField(null=True, blank=True)



