from rest_framework import serializers

from storeApp.models import CabinetAlert


class CabinetAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = CabinetAlert
        fields = [
            "id",
            "cabinet_item_id",
            "kind",
            "title",
            "body",
            "is_read",
            "read_at",
            "created_date",
            "updated_date",
        ]
        read_only_fields = fields
