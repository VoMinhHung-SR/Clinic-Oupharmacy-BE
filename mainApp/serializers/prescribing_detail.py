from rest_framework.serializers import ModelSerializer

from mainApp.models import PrescriptionDetail
from mainApp.serializers.medicine_unit import MedicineUnitSerializer
from mainApp.serializers.prescribing import PrescribingSerializer

class PrescriptionDetailCRUDSerializer(ModelSerializer):
    class Meta:
        model = PrescriptionDetail
        exclude = []

class PrescriptionDetailSerializer(ModelSerializer):
    prescribing = PrescribingSerializer()
    medicine_unit = MedicineUnitSerializer()

    class Meta:
        model = PrescriptionDetail
        exclude = []
