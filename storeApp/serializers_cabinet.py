from rest_framework import serializers

from storeApp.models import Cabinet, CabinetItem, ProductVariant, ProductVariantUnit
from storeApp.models.cabinet import expiration_date_range


def _variant_image_url(variant):
    try:
        if variant and variant.image:
            from mainApp import cloud_context

            return f"{cloud_context}{variant.image}"
        images = getattr(variant, "images", None)
        if variant and images and isinstance(images, list) and images:
            first = images[0]
            url = first.get("url") if isinstance(first, dict) else first
            if not url:
                return None
            if isinstance(url, str) and url.startswith("http"):
                return url
            from mainApp import cloud_context

            return f"{cloud_context}{url}"
    except Exception:
        return None
    return None


class CabinetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cabinet
        fields = ["id", "name", "created_date", "updated_date"]
        read_only_fields = ["id", "created_date", "updated_date"]

    def create(self, validated_data):
        request = self.context["request"]
        return Cabinet.objects.create(user_id=request.user.id, **validated_data)


class CabinetItemSerializer(serializers.ModelSerializer):
    product_variant_id = serializers.PrimaryKeyRelatedField(
        source="product_variant",
        queryset=ProductVariant.objects.all(),
    )
    product_variant_unit_id = serializers.PrimaryKeyRelatedField(
        source="product_variant_unit",
        queryset=ProductVariantUnit.objects.all(),
    )
    expiration_status = serializers.SerializerMethodField()
    days_until_expiry = serializers.SerializerMethodField()
    inventory_status = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    packing = serializers.SerializerMethodField()
    unit_name = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CabinetItem
        fields = [
            "id",
            "cabinet",
            "product_variant_id",
            "product_variant_unit_id",
            "quantity",
            "expiration_date",
            "expiration_status",
            "days_until_expiry",
            "inventory_status",
            "product_name",
            "packing",
            "unit_name",
            "image_url",
            "created_date",
            "updated_date",
        ]
        read_only_fields = [
            "id",
            "expiration_status",
            "days_until_expiry",
            "inventory_status",
            "product_name",
            "packing",
            "unit_name",
            "image_url",
            "created_date",
            "updated_date",
        ]

    def get_expiration_status(self, obj):
        return obj.expiration_status()

    def get_days_until_expiry(self, obj):
        return obj.days_until_expiry()

    def get_inventory_status(self, obj):
        return obj.inventory_status()

    def get_product_name(self, obj):
        try:
            product = obj.product_variant.product
            return product.web_name or product.name
        except Exception:
            return None

    def get_packing(self, obj):
        try:
            return obj.product_variant.packing
        except Exception:
            return None

    def get_unit_name(self, obj):
        try:
            return obj.product_variant_unit.unit_name
        except Exception:
            return None

    def get_image_url(self, obj):
        try:
            return _variant_image_url(obj.product_variant)
        except Exception:
            return None

    def validate(self, attrs):
        request = self.context["request"]
        cabinet = attrs.get("cabinet")
        if self.instance is None:
            if cabinet is None:
                raise serializers.ValidationError({"cabinet": "This field is required."})
            if cabinet.user_id != request.user.id:
                raise serializers.ValidationError({"cabinet": "Not found."})
            variant = attrs.get("product_variant")
            unit = attrs.get("product_variant_unit")
            if variant is None or not variant.is_published:
                raise serializers.ValidationError(
                    {"product_variant_id": "Variant is not available."}
                )
            if unit is None or not unit.is_published or unit.variant_id != variant.id:
                raise serializers.ValidationError(
                    {"product_variant_unit_id": "Unit does not belong to this variant."}
                )
        return attrs

    def update(self, instance, validated_data):
        validated_data.pop("cabinet", None)
        validated_data.pop("product_variant", None)
        validated_data.pop("product_variant_unit", None)
        return super().update(instance, validated_data)


def apply_expiration_status_filter(queryset, status):
    gte, lt = expiration_date_range(status)
    if status not in ("EXPIRED", "EXPIRING_SOON", "EXPIRING", "SAFE"):
        return queryset
    if gte is not None:
        queryset = queryset.filter(expiration_date__gte=gte)
    if lt is not None:
        queryset = queryset.filter(expiration_date__lt=lt)
    return queryset
