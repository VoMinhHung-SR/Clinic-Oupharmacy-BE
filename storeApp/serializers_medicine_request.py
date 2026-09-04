import json

from django.conf import settings
from rest_framework import serializers

from storeApp.models import MedicineRequest, Notification

STORE_DB_ALIAS = "store" if "store" in settings.DATABASES else "default"

MAX_PRESCRIPTION_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}


def prescription_image_url(obj):
    try:
        if not obj.prescription_image:
            return None
        from mainApp import cloud_context

        return f"{cloud_context}{obj.prescription_image}"
    except Exception:
        return None


def emit_medicine_request_notification(lead: MedicineRequest) -> Notification:
    lines = [
        f"MedicineRequest #{lead.pk}",
        f"Họ tên: {lead.full_name}",
        f"Điện thoại: {lead.phone}",
    ]
    if lead.email:
        lines.append(f"Email: {lead.email}")
    if lead.note:
        lines.extend(["", "Ghi chú:", lead.note])
    if lead.items_json:
        lines.extend(["", "Sản phẩm:", json.dumps(lead.items_json, ensure_ascii=False)])
    if lead.prescription_image:
        lines.append("")
        lines.append(f"Ảnh đơn: {prescription_image_url(lead) or str(lead.prescription_image)}")

    return Notification.objects.using(STORE_DB_ALIAS).create(
        notification_type=Notification.ADMIN_SUPPORT,
        title=f"Cần mua thuốc — {lead.full_name}",
        message="\n".join(lines),
        is_read=False,
    )


class MedicineRequestCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=120, allow_blank=False, trim_whitespace=True)
    phone = serializers.CharField(max_length=20, allow_blank=False, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    items_json = serializers.CharField(required=False, allow_blank=True)
    prescription_image = serializers.FileField(required=False, allow_null=True)

    def validate_phone(self, value):
        phone = (value or "").strip()
        if not phone:
            raise serializers.ValidationError("Số điện thoại là bắt buộc.")
        return phone

    def validate_items_json(self, value):
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise serializers.ValidationError("items_json phải là JSON hợp lệ.") from exc
        if not isinstance(parsed, list):
            raise serializers.ValidationError("items_json phải là mảng.")
        return parsed

    def validate_prescription_image(self, value):
        if not value:
            return None
        content_type = getattr(value, "content_type", None) or ""
        if content_type and content_type.lower() not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise serializers.ValidationError("Ảnh đơn chỉ chấp nhận JPEG, PNG, WEBP hoặc GIF.")
        size = getattr(value, "size", None)
        if size is not None and size > MAX_PRESCRIPTION_IMAGE_BYTES:
            raise serializers.ValidationError("Ảnh đơn không được vượt quá 5MB.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        user_id = None
        if request is not None and getattr(request, "user", None) is not None:
            if request.user.is_authenticated:
                user_id = request.user.id

        image = validated_data.pop("prescription_image", None)
        lead = MedicineRequest(
            user_id=user_id,
            full_name=validated_data["full_name"].strip(),
            phone=validated_data["phone"].strip(),
            email=(validated_data.get("email") or "").strip(),
            note=(validated_data.get("note") or "").strip(),
            items_json=validated_data.get("items_json") or [],
            status=MedicineRequest.PENDING,
        )
        if image:
            lead.prescription_image = image
        lead.save(using=STORE_DB_ALIAS)
        notification = emit_medicine_request_notification(lead)
        lead._notification_id = notification.id  # noqa: SLF001 — pass-through for create response
        return lead


class MedicineRequestSerializer(serializers.ModelSerializer):
    prescription_image_url = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = MedicineRequest
        fields = [
            "id",
            "full_name",
            "phone",
            "email",
            "note",
            "items_json",
            "item_count",
            "status",
            "prescription_image_url",
            "created_date",
            "updated_date",
        ]
        read_only_fields = fields

    def get_prescription_image_url(self, obj):
        return prescription_image_url(obj)

    def get_item_count(self, obj):
        items = obj.items_json or []
        return len(items) if isinstance(items, list) else 0
