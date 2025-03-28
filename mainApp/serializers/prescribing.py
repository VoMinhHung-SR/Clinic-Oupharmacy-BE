from rest_framework.serializers import ModelSerializer

from mainApp.models import Prescribing

from rest_framework import serializers

class PrescribingSerializer(ModelSerializer):
    bill_status = serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = Prescribing
        exclude = []

    def get_bill_status(self, obj):
        bill_instance = obj.bill_set.first()
        if bill_instance:
            return {'id': bill_instance.id, 'amount': bill_instance.amount}
        return None
