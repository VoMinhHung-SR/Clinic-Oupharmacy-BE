from rest_framework.serializers import ModelSerializer

from mainApp.models import Examination
from mainApp.serializers.diagnosis import DiagnosisStatusSerializer
from mainApp.serializers.patient import PatientSerializer
from mainApp.serializers.user import UserSerializer, UserNormalSerializer

from rest_framework import serializers


class ExaminationSerializer(ModelSerializer):
    patient_id = serializers.IntegerField(write_only=True)

    patient = PatientSerializer(read_only=True)
    user = UserSerializer()
    schedule_appointment = serializers.SerializerMethodField(source="time_slot")
    diagnosis_info = DiagnosisStatusSerializer(many=True, read_only=True, source='diagnosis_set')

    def get_schedule_appointment(self, obj):
        if obj.time_slot:
            doctor_schedule = obj.time_slot.schedule  # Schedule
            if doctor_schedule:
                doctor_info = doctor_schedule.doctor
                if doctor_info:
                    return {
                        'id': obj.time_slot.id,  # ID of appointment
                        'day': doctor_schedule.date,
                        'start_time': obj.time_slot.start_time,
                        'end_time': obj.time_slot.end_time,
                        'doctor_id': doctor_info.id,
                        'email': doctor_info.email,
                        'first_name': doctor_info.first_name,
                        'last_name': doctor_info.last_name
                    }
        return {}

    def to_internal_value(self, data):
        # Map the patient_id to the patient field
        data['patient'] = {'id': data.pop('patient_id', None)}
        return super().to_internal_value(data)

    class Meta:
        model = Examination
        fields = ["id", "active", "created_date", "updated_date", "description", 'mail_status',
                  'time_slot', 'user', 'patient', 'patient_id', 'wage',
                  'reminder_email', 'schedule_appointment', 'diagnosis_info']
        exclude = []
        extra_kwargs = {
            'schedule_appointment': {'read_only': 'true'},
            'time_slot': {'write_only': 'true'}
        }


class DoctorAvailabilitySerializer:
    pass


class ExaminationsPairSerializer(ModelSerializer):
    user = UserNormalSerializer()
    patient = PatientSerializer()
    doctor_availability = DoctorAvailabilitySerializer()

    class Meta:
        model = Examination
        fields = ['id', 'user', 'patient', 'description', 'doctor_availability', 'created_date']