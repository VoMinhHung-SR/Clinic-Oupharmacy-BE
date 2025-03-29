from rest_framework.serializers import ModelSerializer

from mainApp.models import TimeSlot


class TimeSlotSerializer(ModelSerializer):
    class Meta:
        model = TimeSlot
        exclude = []