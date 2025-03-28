from rest_framework.serializers import ModelSerializer

from mainApp.models import Diagnosis
from mainApp.serializers.examination import ExaminationSerializer
from mainApp.serializers.patient import PatientSerializer
from mainApp.serializers.prescribing import PrescribingSerializer
from mainApp.serializers.user import UserNormalSerializer

class DiagnosisCRUDSerializer(ModelSerializer):
    class Meta:
        model = Diagnosis
        exclude = []

class DiagnosisStatusSerializer(ModelSerializer):
    class Meta:
        model = Diagnosis
        fields = ["id", "sign", "diagnosed"]
        
class DiagnosisSerializer(ModelSerializer):
    examination = ExaminationSerializer()
    user = UserNormalSerializer()
    patient = PatientSerializer()
    prescribing_info = PrescribingSerializer(many=True, read_only=True, source='prescribing_set')

    class Meta:
        model = Diagnosis
        exclude = []