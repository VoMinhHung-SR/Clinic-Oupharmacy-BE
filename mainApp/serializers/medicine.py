from rest_framework.serializers import ModelSerializer

from mainApp.models import Medicine


class MedicineSerializer(ModelSerializer):
    class Meta:
        model = Medicine
        fields = ["id", "name", "effect", "contraindications"]
