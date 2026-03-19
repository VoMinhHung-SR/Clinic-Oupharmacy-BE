import os
from django.conf import settings
from rest_framework.serializers import ModelSerializer
from . import cloud_context
from .constant import CLOUDINARY_DEFAULT_AVATAR, LIMIT_USER_LOCATION, ROLE_DOCTOR
from .models import *
from rest_framework import serializers
import cloudinary.uploader

class UserRoleSerializer(ModelSerializer):
    class Meta:
        model = UserRole
        exclude = ['active']


class CommonCitySerializer(ModelSerializer):
    class Meta:
        model = CommonCity
        fields = ["id", "name"]


class CommonDistrictSerializer(ModelSerializer):
    city = CommonCitySerializer()

    class Meta:
        model = CommonDistrict
        fields = ["id", "name", "city"]


class UserAddressSerializer(ModelSerializer):
    district_info = serializers.SerializerMethodField(source='district')
    city_info = serializers.SerializerMethodField(source='city')

    def get_district_info(self, obj):
        district = obj.district
        if district:
            return {'id': district.id, 'name': district.name}
        return {}

    def get_city_info(self, obj):
        city = obj.city
        if city:
            return {'id': city.id, 'name': city.name}
        return {}

    def validate_address(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Địa chỉ không được để trống.")
        return value.strip()

    def _clear_other_default(self, user, exclude_pk=None):
        qs = UserAddress.objects.filter(user=user)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        qs.update(is_default=False)

    def create(self, validated_data):
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Bạn cần đăng nhập để thêm địa chỉ.")
        if user.addresses.count() >= LIMIT_USER_LOCATION:
            raise serializers.ValidationError(
                {"address": f"Tối đa {LIMIT_USER_LOCATION} địa chỉ. Vui lòng xóa bớt trước khi thêm mới."}
            )
        if validated_data.get('is_default'):
            self._clear_other_default(user)
        validated_data['user'] = user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get('is_default'):
            self._clear_other_default(instance.user, exclude_pk=instance.pk)
        return super().update(instance, validated_data)

    class Meta:
        model = UserAddress
        fields = ["id", "address", "lat", "lng", "city", "district", "district_info", "city_info", "is_default"]
        extra_kwargs = {
            'city': {'write_only': True},
            'district': {'write_only': True},
            'district_info': {'read_only': True},
            'city_info': {'read_only': True},
        }


class UserSerializer(ModelSerializer):

    def create(self, validated_data):
        avatar_file = validated_data.pop('avatar', None)
        user = User(**validated_data)
        user.set_password(user.password)
        user.save()
        if avatar_file:
            if hasattr(avatar_file, 'read'):
                upload_result = cloudinary.uploader.upload(avatar_file)
                user.avatar = upload_result['public_id']
            else:
                user.avatar = avatar_file
        else:
            user.avatar = CLOUDINARY_DEFAULT_AVATAR
        user.save()

        return user

    def update(self, instance, validated_data):
        avatar_file = validated_data.pop('avatar', None)
        if avatar_file:
            upload_result = cloudinary.uploader.upload(avatar_file)
            instance.avatar = upload_result['public_id']
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            data['role'] = UserRole.objects.get(id=data['role']).name
        except:
            data['role'] = None
        return data

    addresses = serializers.SerializerMethodField()
    defaultAddress = serializers.SerializerMethodField()

    def get_addresses(self, obj):
        qs = getattr(obj, 'addresses', None)
        if qs is None:
            return []
        addresses = list(qs.all()[:LIMIT_USER_LOCATION])
        return UserAddressSerializer(addresses, many=True).data

    def get_defaultAddress(self, obj):
        default = getattr(obj, 'addresses', None)
        if default is None:
            return None
        addr = default.filter(is_default=True).first() or default.first()
        return UserAddressSerializer(addr).data if addr else None

    avatar_path = serializers.SerializerMethodField(source='avatar')

    def get_avatar_path(self, obj):
        if obj.avatar:
            avatar_str = str(obj.avatar)
            if 'https://' in avatar_str or 'http://' in avatar_str:
                if 'image/upload/' in avatar_str:
                    url_part = avatar_str.split('image/upload/')[-1]
                    return url_part
                else:
                    return avatar_str
            else:
                path = "{cloud_context}{image_name}".format(cloud_context=cloud_context,
                                                            image_name=obj.avatar)
                return path
        return None

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "password",
                  "email", "phone_number", "date_of_birth", "addresses", "defaultAddress",
                  "date_joined", "gender", "avatar_path", "avatar", "is_admin", "role"]
        extra_kwargs = {
            'password': {'write_only': 'true'},
            'avatar_path': {'read_only': 'true'},
            'addresses': {'read_only': 'true'},
            'defaultAddress': {'read_only': 'true'},
            'avatar': {'write_only': 'true'}
        }

class UserDisplaySerializer(serializers.ModelSerializer):
    avatar_path = serializers.SerializerMethodField(source='avatar')
    def get_avatar_path(self, obj):
        if obj.avatar:
            avatar_str = str(obj.avatar)
            if 'https://' in avatar_str or 'http://' in avatar_str:
                if 'image/upload/' in avatar_str:
                    url_part = avatar_str.split('image/upload/')[-1]
                    return url_part
                else:
                    return avatar_str
            else:
                path = "{cloud_context}{image_name}".format(cloud_context=cloud_context,
                                                            image_name=obj.avatar)
                return path
        return None

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', "avatar_path"]

        extra_kwargs = {
            'avatar_path': {'read_only': 'true'}
        }

class SpecializationTagSerializer(ModelSerializer):
    class Meta:
        model = SpecializationTag
        fields = ["id", "name"]

class DoctorProfileSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__name=ROLE_DOCTOR,is_active=True),
        write_only=True
    )
    user_display = UserDisplaySerializer(source='user', read_only=True)

    specialization_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SpecializationTag.objects.all(),
        source='specializations',
        write_only=True
    )
    specializations = SpecializationTagSerializer(many=True, read_only=True)
    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "user",               # input
            "user_display",       # output
            "description",
            "specialization_ids", # input
            "specializations"     # output
        ]

class CategorySerializer(ModelSerializer):
    category_array = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "level", "path", "path_slug", "category_array"]
    
    def get_category_array(self, obj):
        """Trả về category array format theo schema"""
        if hasattr(obj, 'get_category_array'):
            return obj.get_category_array()
        return []


class MedicineSerializer(ModelSerializer):
    class Meta:
        model = Medicine
        fields = [
            "id", "name", "mid", "slug", "web_name", 
            "description", "ingredients", "usage", "dosage", 
            "adverse_effect", "careful", "preservation", 
            "brand_id"
        ]


class MedicineUnitSerializer(ModelSerializer):
    image_path = serializers.SerializerMethodField()
    medicine = serializers.PrimaryKeyRelatedField(queryset=Medicine.objects.all())
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())

    def create(self, validated_data):
        image_file = validated_data.pop('image', None)
        if image_file:
            upload_result = cloudinary.uploader.upload(image_file)
            validated_data['image'] = upload_result['public_id']
        return MedicineUnit.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        image_file = validated_data.pop('image', None)
        if image_file:
            upload_result = cloudinary.uploader.upload(image_file)
            instance.image = upload_result['public_id']
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    class Meta:
        model = MedicineUnit
        fields = [
            "id", "in_stock", "image", "image_path", "images",
            "price_display", "price_value", "original_price_value",
            "package_size", "product_ranking", "display_code",
            "is_published", "is_hot", "registration_number", "origin", "manufacturer",
            "shelf_life", "specifications", "medicine", "category",
            "created_date", "updated_date"
        ]
        extra_kwargs = {
            'image_path': {'read_only': True},
            'image': {'write_only': True}
        }

    def get_image_path(self, obj):
        if obj.image:
            path = '{cloud_context}{image_name}'.format(cloud_context=cloud_context, image_name=obj.image)
            return path
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['medicine'] = MedicineSerializer(instance.medicine).data
        representation['category'] = CategorySerializer(instance.category).data
        return representation

class MedicineUnitOptionSerializer(serializers.ModelSerializer):

    class Meta:
        model = MedicineUnit
        fields = [
            "id",
            "package_size",
            "price_display",
            "price_value",
            "original_price_value",
            "in_stock",
            "is_hot",
        ]
    
from rest_framework import serializers


class MedicineWithUnitsSerializer(serializers.ModelSerializer):

    medicine = MedicineSerializer(read_only=True)
    category = serializers.SerializerMethodField()
    package_options = serializers.SerializerMethodField()

    package_size = serializers.SerializerMethodField()
    price_display = serializers.SerializerMethodField()
    price_value = serializers.SerializerMethodField()
    original_price_value = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    is_hot = serializers.SerializerMethodField()

    class Meta:
        model = Medicine
        fields = [
            "id",

            "package_size",
            "price_display",
            "price_value",
            "original_price_value",
            "in_stock",
            "is_hot",

            "medicine",
            "category",
            "package_options"
        ]

    def get_default_unit(self, obj):
        if not hasattr(obj, "_default_unit"):
            obj._default_unit = next(iter(obj.units.all()), None)
        return obj._default_unit

    def get_package_size(self, obj):
        unit = self.get_default_unit(obj)
        return unit.package_size if unit else None

    def get_price_display(self, obj):
        unit = self.get_default_unit(obj)
        return unit.price_display if unit else None

    def get_price_value(self, obj):
        unit = self.get_default_unit(obj)
        return unit.price_value if unit else None

    def get_original_price_value(self, obj):
        unit = self.get_default_unit(obj)
        return unit.original_price_value if unit else None

    def get_in_stock(self, obj):
        unit = self.get_default_unit(obj)
        return unit.in_stock if unit else None

    def get_is_hot(self, obj):
        unit = self.get_default_unit(obj)
        return unit.is_hot if unit else None

    def get_package_options(self, obj):
        units = obj.units.all()
        return MedicineUnitOptionSerializer(units, many=True).data

    def get_category(self, obj):
        unit = self.get_default_unit(obj)
        if unit and unit.category:
            return CategorySerializer(unit.category).data
        return None
    
class DoctorScheduleSerializer(ModelSerializer):
    class Meta:
        model = DoctorSchedule
        exclude = []

class TimeSlotSerializer(ModelSerializer):
    class Meta:
        model = TimeSlot
        exclude = []

class PatientSerializer(ModelSerializer):
    class Meta:
        model = Patient
        exclude = ["created_date", "updated_date"]

class DiagnosisStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Diagnosis
        fields = ["id", "sign", "diagnosed"]

class ExaminationSerializer(ModelSerializer):
    patient_id = serializers.IntegerField(write_only=True)

    patient = PatientSerializer(read_only=True)
    user = UserSerializer()
    schedule_appointment = serializers.SerializerMethodField(source="time_slot")
    diagnosis_info = DiagnosisStatusSerializer(many=True, read_only=True, source='diagnosis_set')

    def get_schedule_appointment(self, obj):
        if obj.time_slot:
            doctor_schedule = obj.time_slot.schedule  # Schedule
            if doctor_schedule:
                doctor_info = doctor_schedule.doctor
                if doctor_info:
                    return {
                        'id': obj.time_slot.id,  # ID of appointment
                        'day': doctor_schedule.date,
                        'start_time': obj.time_slot.start_time,
                        'end_time': obj.time_slot.end_time,
                        'doctor_id': doctor_info.id,
                        'email': doctor_info.email,
                        'first_name': doctor_info.first_name,
                        'last_name': doctor_info.last_name
                    }
        return {}

    def to_internal_value(self, data):
        # Map the patient_id to the patient field
        data['patient'] = {'id': data.pop('patient_id', None)}
        return super().to_internal_value(data)

    class Meta:
        model = Examination
        fields = ["id", "created_date", "updated_date", "description", 'mail_status',
                  'time_slot', 'user', 'patient', 'patient_id', 'wage',
                  'reminder_email', 'schedule_appointment', 'diagnosis_info']
        exclude = []
        extra_kwargs = {
            'schedule_appointment': {'read_only': 'true'},
            'time_slot': {'write_only': 'true'}
        }

class UserNormalSerializer(ModelSerializer):
    addresses = serializers.SerializerMethodField()
    defaultAddress = serializers.SerializerMethodField()

    def get_addresses(self, obj):
        qs = getattr(obj, 'addresses', None)
        if qs is None:
            return []
        return UserAddressSerializer(qs.all()[:LIMIT_USER_LOCATION], many=True).data

    def get_defaultAddress(self, obj):
        default = getattr(obj, 'addresses', None)
        if default is None:
            return None
        addr = default.filter(is_default=True).first() or default.first()
        return UserAddressSerializer(addr).data if addr else None

    class Meta:
        model = User
        fields = ['id', "first_name", "last_name", "email", "addresses", "defaultAddress"]
        extra_kwargs = {
            'addresses': {'read_only': 'true'},
            'defaultAddress': {'read_only': 'true'}
        }

class PrescribingSerializer(ModelSerializer):
    bill_status = serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = Prescribing
        exclude = []

    def get_bill_status(self, obj):
        # Assuming 'bill' is the ForeignKey relation from Prescribing to Bill
        bill_instance = obj.bill_set.first()
        if bill_instance:
            return {'id': bill_instance.id, 'amount': bill_instance.amount}
        return None

class DiagnosisSerializer(ModelSerializer):
    examination = ExaminationSerializer()
    user = UserNormalSerializer()
    patient = PatientSerializer()
    prescribing_info = PrescribingSerializer(many=True, read_only=True, source='prescribing_set')

    class Meta:
        model = Diagnosis
        exclude = []

class DiagnosisCRUDSerializer(ModelSerializer):
    class Meta:
        model = Diagnosis
        exclude = []

class PrescriptionDetailCRUDSerializer(ModelSerializer):
    class Meta:
        model = PrescriptionDetail
        exclude = []

class PrescriptionDetailSerializer(ModelSerializer):
    prescribing = PrescribingSerializer()
    medicine_unit = MedicineUnitSerializer()

    class Meta:
        model = PrescriptionDetail
        exclude = []

class BillSerializer(ModelSerializer):
    class Meta:
        model = Bill
        fields = ["id", "amount", "prescribing"]

class ExaminationsPairSerializer(ModelSerializer):
    user = UserNormalSerializer()
    patient = PatientSerializer()

    class Meta:
        model = Examination
        fields = ['id', 'user', 'patient', 'description', 'created_date']

class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True)
    message = serializers.CharField()