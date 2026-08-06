"""Serializers for Campaign admin API (P1-T3)."""

from rest_framework import serializers

from storeApp.models import Campaign, CampaignPlacement


class CampaignPlacementSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignPlacement
        fields = [
            "id",
            "slot",
            "title",
            "subtitle",
            "cta_label",
            "cta_url",
            "image_desktop_url",
            "image_mobile_url",
            "image_alt",
            "sort_order",
            "is_enabled",
        ]
        read_only_fields = ["id"]

    def validate_cta_url(self, value):
        if value in (None, ""):
            return value
        if value.startswith("http://") or value.startswith("https://"):
            raise serializers.ValidationError("CTA URL must be a relative path in v1")
        if not value.startswith("/"):
            raise serializers.ValidationError("CTA URL must start with /")
        return value


class CampaignSerializer(serializers.ModelSerializer):
    placements = CampaignPlacementSerializer(many=True, read_only=True)

    class Meta:
        model = Campaign
        fields = [
            "id",
            "name",
            "slug",
            "title",
            "subtitle",
            "description_html",
            "status",
            "priority",
            "start_at",
            "end_at",
            "locale",
            "created_by_id",
            "updated_by_id",
            "version",
            "placements",
            "created_date",
            "updated_date",
            "active",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_by_id",
            "updated_by_id",
            "version",
            "placements",
            "created_date",
            "updated_date",
        ]


class CampaignWriteSerializer(serializers.ModelSerializer):
    """Create / PATCH body (status via actions only)."""

    class Meta:
        model = Campaign
        fields = [
            "name",
            "slug",
            "title",
            "subtitle",
            "description_html",
            "priority",
            "start_at",
            "end_at",
            "locale",
            "version",
        ]
        extra_kwargs = {"version": {"required": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            for name in ("name", "slug", "title"):
                self.fields[name].required = False

    def validate(self, attrs):
        start_at = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end_at = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start_at is not None and end_at is not None and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "end_at must be after start_at"})
        return attrs


class CampaignPlacementsReplaceSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    placements = CampaignPlacementSerializer(many=True)


class CampaignActionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
