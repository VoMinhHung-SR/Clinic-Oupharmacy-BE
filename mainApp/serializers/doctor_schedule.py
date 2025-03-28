from rest_framework.serializers import ModelSerializer

from mainApp.models import DoctorSchedule


class DoctorScheduleSerializer(ModelSerializer):
    class Meta:
        model = DoctorSchedule
        exclude = []