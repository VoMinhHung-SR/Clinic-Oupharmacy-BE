from rest_framework import serializers

from storeApp.models.consultation import ConsultationSession
from storeApp.services.consultation.session_create import get_or_create_open_session


class ConsultationSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsultationSession
        fields = [
            "id",
            "user_id",
            "pharmacist_id",
            "status",
            "firestore_conversation_id",
            "need_text",
            "context_json",
            "created_date",
            "updated_date",
            "active",
        ]
        read_only_fields = fields


class ConsultationSessionCreateSerializer(serializers.Serializer):
    need_text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    context_json = serializers.JSONField(required=False)
    firestore_conversation_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=128,
        trim_whitespace=True,
    )

    def create(self, validated_data):
        request = self.context["request"]
        session, created = get_or_create_open_session(
            user_id=request.user.id,
            need_text=(validated_data.get("need_text") or "").strip(),
            context_json=validated_data.get("context_json") or {},
            firestore_conversation_id=(validated_data.get("firestore_conversation_id") or "").strip(),
        )
        # Stash for ViewSet to pick 200 vs 201.
        self._session_created = created
        return session


class ConsultationSessionPatchSerializer(serializers.Serializer):
    """Allow owner/pharmacist to attach Firestore conversation id after client creates it."""

    firestore_conversation_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=128,
        trim_whitespace=True,
    )
    need_text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    context_json = serializers.JSONField(required=False)
