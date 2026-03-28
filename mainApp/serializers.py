import os
from django.conf import settings
from rest_framework.serializers import ModelSerializer
from . import cloud_context
from .constant import CLOUDINARY_DEFAULT_AVATAR, LIMIT_USER_LOCATION, ROLE_DOCTOR
from .models import *
from rest_framework import serializers
from storeApp.models import ProductVariant, ProductVariantUnit
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
 
    prescribing = serializers.PrimaryKeyRelatedField(queryset=Prescribing.objects.filter(active=True))
    product_variant_id = serializers.IntegerField(required=False, allow_null=True)
    product_variant_unit_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = PrescriptionDetail
        fields = ["id", "active", "created_date", "updated_date",
        "quantity", "uses", "prescribing", "product_variant_id",
        "product_variant_unit_id"]
      
        read_only_fields = ["id", "created_date", "updated_date", "active"]

class PrescriptionDetailSerializer(ModelSerializer):

    prescribing = PrescribingSerializer()
    product_variant = serializers.SerializerMethodField()
    product_variant_unit = serializers.SerializerMethodField()

    class Meta:
        model = PrescriptionDetail
        exclude = []

    def _serialize_store_variant(self, *, variant, unit_price_value=None, unit_name=None, unit_quantity_in_base=None):
        """
        Build a lightweight object that matches what FE adapter expects.
        Shape target (see FE normalizeStoreVariant/normalizePrescriptionDetailItem):
        - product: {id, name, web_name}
        - packing/package_size: string
        - price_value: number
        - in_stock: number
        - category: {id, name}
        """
        product = getattr(variant, "product", None)
        category = getattr(product, "category", None) if product else None
        return {
            "id": variant.id,
            "product_id": product.id if product else None,
            "product": {
                "id": product.id if product else None,
                "name": getattr(product, "name", None),
                "web_name": getattr(product, "web_name", None),
            }
            if product
            else None,
            "packing": getattr(variant, "packing", None),
            "price_value": unit_price_value if unit_price_value is not None else 0,
            "unit_name": unit_name,
            "quantity_in_base": unit_quantity_in_base,
            "in_stock": int(getattr(variant, "in_stock", None) or 0),
            "category": ({"id": category.id, "name": category.name} if category else None),
        }

    def get_product_variant_unit(self, obj):
        unit_id = getattr(obj, "product_variant_unit_id", None)
        if not unit_id:
            return None

        pvu = (
            ProductVariantUnit.objects.using("store")
            .select_related("variant__product__category")
            .filter(id=unit_id, is_published=True)
            .first()
        )
        if not pvu:
            # Fallback: still allow FE to show something from snapshots
            variant = ProductVariant.objects.using("store").filter(id=obj.product_variant_id).first()
            if not variant:
                return None
            return self._serialize_store_variant(
                variant=variant,
                unit_price_value=(obj.unit_price_snapshot if obj.unit_price_snapshot is not None else 0),
                unit_name=obj.unit_name_snapshot,
                unit_quantity_in_base=getattr(obj, "quantity_in_base_snapshot", None),
            )

        variant = pvu.variant
        payload = self._serialize_store_variant(
            variant=variant,
            unit_price_value=(pvu.price_value if pvu.price_value is not None else 0),
            unit_name=getattr(pvu, "unit_name", None),
            unit_quantity_in_base=getattr(pvu, "quantity_in_base", None),
        )
        payload.update({
            # Put unit id at the top so normalizeStoreVariant can keep `id`
            # consistent with other payloads.
            "id": pvu.id,
            "price_display": pvu.price_display,
            "unit_order": getattr(pvu, "unit_order", None),
            "is_default": pvu.is_default,
            "is_published": pvu.is_published,
        })
        return payload

    def get_product_variant(self, obj):
        variant_id = getattr(obj, "product_variant_id", None)
        if not variant_id:
            return None

        variant = (
            ProductVariant.objects.using("store")
            .select_related("product__category")
            .filter(id=variant_id, active=True)
            .first()
        )
        if not variant:
            return None

        # Prefer snapshot values for price; otherwise use default/published unit.
        unit_price = obj.unit_price_snapshot if obj.unit_price_snapshot is not None else None
        unit_name = obj.unit_name_snapshot
        unit_quantity_in_base = getattr(obj, "quantity_in_base_snapshot", None)

        if unit_price is None:
            pvu = (
                ProductVariantUnit.objects.using("store")
                .filter(variant_id=variant.id, is_default=True, is_published=True)
                .first()
                or ProductVariantUnit.objects.using("store")
                .filter(variant_id=variant.id, is_published=True)
                .order_by("unit_order", "id")
                .first()
            )
            if pvu:
                unit_price = pvu.price_value
                unit_name = pvu.unit_name
                unit_quantity_in_base = pvu.quantity_in_base

        return self._serialize_store_variant(
            variant=variant,
            unit_price_value=(unit_price if unit_price is not None else 0),
            unit_name=unit_name,
            unit_quantity_in_base=unit_quantity_in_base,
        )

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