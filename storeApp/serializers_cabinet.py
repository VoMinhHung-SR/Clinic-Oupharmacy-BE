import re

from rest_framework import serializers

from storeApp.models import Cabinet, CabinetItem, ProductVariant, ProductVariantUnit
from storeApp.models.cabinet import DOSE_TIMES_MAX, expiration_date_range

DOSE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def variant_image_url(variant):
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


# Back-compat alias for older imports
_variant_image_url = variant_image_url


class CabinetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cabinet
        fields = [
            "id",
            "name",
            "reminder_enabled",
            "expiring_soon_days",
            "created_date",
            "updated_date",
        ]
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
            "lot_number",
            "low_stock_threshold",
            "on_refill_list",
            "dose_enabled",
            "dose_times",
            "dose_label",
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
            return variant_image_url(obj.product_variant)
        except Exception:
            return None

    def validate_lot_number(self, value):
        if value == "":
            return None
        return value

    def validate_dose_times(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list of HH:MM strings.")
        normalized = set()
        for raw in value:
            if not isinstance(raw, str) or not DOSE_TIME_RE.match(raw.strip()):
                raise serializers.ValidationError(f"Invalid time: {raw!r}. Use HH:MM (24h).")
            normalized.add(raw.strip())
        if len(normalized) > DOSE_TIMES_MAX:
            raise serializers.ValidationError(f"At most {DOSE_TIMES_MAX} times per day.")
        return sorted(normalized)

    def validate_dose_label(self, value):
        return (value or "").strip()

    def validate(self, attrs):
        request = self.context["request"]
        dose_enabled = attrs.get(
            "dose_enabled", getattr(self.instance, "dose_enabled", False)
        )
        dose_times = attrs.get("dose_times", getattr(self.instance, "dose_times", None) or [])
        if dose_enabled and not dose_times:
            raise serializers.ValidationError(
                {"dose_times": "At least one time is required when dose reminders are enabled."}
            )
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


def apply_expiration_status_filter(queryset, status, soon_days=None):
    gte, lt = expiration_date_range(status, soon_days=soon_days)
    if status not in ("EXPIRED", "EXPIRING_SOON", "EXPIRING", "SAFE"):
        return queryset
    if gte is not None:
        queryset = queryset.filter(expiration_date__gte=gte)
    if lt is not None:
        queryset = queryset.filter(expiration_date__lt=lt)
    return queryset
