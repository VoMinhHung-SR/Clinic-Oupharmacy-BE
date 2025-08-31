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
    name = models.CharField(max_length=254, null=False, blank=False, unique=True)
    effect = models.CharField(max_length=254, null=True, blank=True)
    contraindications = models.CharField(max_length=254, null=True, blank=True)

    def __str__(self):
        return self.name


class Category(BaseModel):
    name = models.CharField(max_length=254, null=False, blank=False, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class MedicineUnit(BaseModel):
    price = models.FloatField(null=False)
    in_stock = models.IntegerField(null=False)
    image = CloudinaryField('medicines', default='', null=True, folder='OUPharmacy/medicines/image')
    packaging = models.CharField(max_length=50, null=True)
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)


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



