"""
Checkout delivery payload: validate structured `delivery` and format `Order.shipping_address` text.

Legacy clients send `shipping_address` as a non-empty string; that path is unchanged.
"""

import re

from django.core.validators import RegexValidator
from rest_framework import serializers

_VN_PHONE_RE = re.compile(
    r"^(0|\+?84)(2(0[3-9]|1[0-6|8|9]|2[0-2|5-9]|3[2-9]|4[0-9]|5[1|2|4-9]|6[0-3|9]|7[0-7]|8[0-9]|9[0-4|6|7|9])"
    r"|3[2-9]|5[5|6|8|9]|7[0|6-9]|8[0-6|8|9]|9[0-4|6-9])([0-9]{7})$"
)
_ADDRESS_DETAIL_RE = re.compile(
    r"^[a-zA-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠàáâãèéêìíòóôõùúăđĩũơ"
    r"ƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂẾưăạảấầẩẫậắằẳẵặẹẻẽềềểỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪễệếỉịọỏốồổỗộớờởỡợụủứừỬỮỰỲỴÝỶỸửữựýỳỵỷỹ0-9,-/;|:\s]*$"
)


def _trimmed_non_empty(value: str) -> str:
    s = (value or "").strip()
    if len(s) < 2:
        raise serializers.ValidationError("Must be at least 2 characters.")
    if len(s) > 254:
        raise serializers.ValidationError("Must be at most 254 characters.")
    return s


def _phone_field():
    return serializers.CharField(
        trim_whitespace=True,
        max_length=20,
        validators=[RegexValidator(_VN_PHONE_RE, message="Invalid Vietnamese phone number.")],
    )


def _optional_region():
    return serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=120,
        default="",
    )


class CheckoutOrdererSerializer(serializers.Serializer):
    name = serializers.CharField(trim_whitespace=True, max_length=254)
    phone = _phone_field()
    email = serializers.EmailField(required=False, allow_blank=True, trim_whitespace=True, max_length=254)

    def validate_name(self, value):
        return _trimmed_non_empty(value)

    def validate_email(self, value):
        if not value or not str(value).strip():
            return ""
        return str(value).strip()


class CheckoutRecipientSerializer(serializers.Serializer):
    name = serializers.CharField(trim_whitespace=True, max_length=254)
    phone = _phone_field()

    def validate_name(self, value):
        return _trimmed_non_empty(value)


class CheckoutAddressSerializer(serializers.Serializer):
    province = _optional_region()
    district = _optional_region()
    ward = _optional_region()
    detail = serializers.CharField(trim_whitespace=True, max_length=500)

    def validate_detail(self, value):
        s = (value or "").strip()
        if len(s) < 5:
            raise serializers.ValidationError("Detail address must be at least 5 characters.")
        if not _ADDRESS_DETAIL_RE.match(s):
            raise serializers.ValidationError("Detail address contains invalid characters.")
        return s


class CheckoutDeliverySerializer(serializers.Serializer):
    """Structured checkout delivery; used when `delivery` object is sent instead of legacy string."""

    orderer = CheckoutOrdererSerializer()
    recipient = CheckoutRecipientSerializer()
    address = CheckoutAddressSerializer()


def format_shipping_address_text(validated: dict) -> str:
    """
    Build multiline shipping_address from CheckoutDeliverySerializer.validated_data.
    """
    orderer = validated["orderer"]
    recipient = validated["recipient"]
    addr = validated["address"]

    lines = [
        f"Người đặt: {orderer['name']} — {orderer['phone']}",
    ]
    email = orderer.get("email") or ""
    if email:
        lines.append(f"Email người đặt: {email}")

    lines.append(f"Người nhận: {recipient['name']} — {recipient['phone']}")

    region_parts = [p for p in (addr.get("province") or "", addr.get("district") or "", addr.get("ward") or "") if p]
    if region_parts:
        lines.append("Địa chỉ hành chính sau sáp nhập: " + ", ".join(region_parts))

    lines.append(f"Địa chỉ cụ thể: {addr['detail']}")
    return "\n".join(lines)


def resolve_checkout_shipping_address(*, shipping_address, delivery) -> tuple[str | None, dict | None]:
    """
    Decide shipping_address string for checkout.

    - Non-empty legacy string `shipping_address` wins (backward compatible).
    - Else validate `delivery` dict and return formatted string.
    - Returns (text, errors) where errors is DRF-style dict for 400 response, or None on success.
    """
    if isinstance(shipping_address, str) and shipping_address.strip():
        return shipping_address.strip(), None

    if delivery is None:
        return None, {
            "shipping_address": ["shipping_address (non-empty string) or delivery object is required."],
        }

    if not isinstance(delivery, dict):
        return None, {"delivery": ["delivery must be a JSON object."]}

    ser = CheckoutDeliverySerializer(data=delivery)
    if not ser.is_valid():
        return None, ser.errors

    return format_shipping_address_text(ser.validated_data), None
