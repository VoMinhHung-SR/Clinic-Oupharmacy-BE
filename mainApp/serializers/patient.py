from rest_framework.serializers import ModelSerializer

from mainApp.models import Patient


class PatientSerializer(ModelSerializer):
    class Meta:
        model = Patient
        exclude = ["created_date", "updated_date"]