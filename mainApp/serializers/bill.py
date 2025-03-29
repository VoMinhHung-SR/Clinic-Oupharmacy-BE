from rest_framework.serializers import ModelSerializer

from mainApp.models import Bill


class BillSerializer(ModelSerializer):
    class Meta:
        model = Bill
        fields = ["id", "amount", "prescribing"]