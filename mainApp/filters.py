import django_filters
from django.db.models import CharField, Value
from django.db.models.functions import Concat
from .models import *

class PatientFilter(django_filters.FilterSet):
    patient_name = django_filters.CharFilter(method='filter_patient_name')

    class Meta:
        model = Patient
        fields = ['patient_name']

    def filter_patient_name(self, queryset, name, value):
        return queryset.filter(self_first_name__icontains=value) | queryset.filter(
            self_last_name__icontains=value)


class ExaminationFilter(django_filters.FilterSet):
    kw = django_filters.CharFilter(field_name="user__email")
    status = django_filters.BooleanFilter(field_name="mail_status")

    has_diagnosis = django_filters.BooleanFilter(method='filter_has_diagnosis')

    class Meta:
        model = Examination
        fields = ('kw', 'status', 'has_diagnosis')

    def filter_has_diagnosis(self, queryset, name, value):
        if value:
            return queryset.filter(diagnosis__isnull=False)
        else:
            return queryset.filter(diagnosis__isnull=True)

class MedicineUnitFilter(django_filters.FilterSet):
    kw = django_filters.CharFilter(field_name="medicine__name", lookup_expr="icontains")
    cate = django_filters.NumberFilter(field_name="category__id")
    price = django_filters.CharFilter(method="filter_price")

    class Meta:
        model = MedicineUnit
        fields = ['kw', 'cate', 'price']

    def filter_price(self, queryset, name, value):
        if value == "asc":
            return queryset.order_by("price")
        elif value == "desc":
            return queryset.order_by("-price")
        return queryset


class DiagnosisFilter(django_filters.FilterSet):
    has_prescription = django_filters.BooleanFilter(method='filter_has_prescription')
    has_payment = django_filters.BooleanFilter(method='filter_bill')
    patient_name = django_filters.CharFilter(method='filter_patient_name')
    doctor_name = django_filters.CharFilter(method='filter_doctor_name')
    # Can add another fields to filter
    class Meta:
        model = Diagnosis
        fields = ('has_payment', 'has_prescription', 'doctor_name', 'patient_name')

    def filter_has_prescription(self, queryset, name, value):
        if value:
            # Filter for Diagnoses that have associated Prescribing instances
            return queryset.filter(prescribing__isnull=False).distinct()
        else:
            # Filter for Diagnoses that do not have associated Prescribing instances
            return queryset.filter(prescribing__isnull=True)

    def filter_bill(self, queryset, name, value):
        if value:
            # Filter for Diagnoses that have associated Bill instances
            return queryset.filter(prescribing__bill__isnull=False).distinct()
        else:
            # Filter for Diagnoses that do not have associated Bill instances
            return queryset.filter(prescribing__bill__isnull=True)

    def filter_patient_name(self, queryset, name, value):
        combined_name = value.strip()  # Remove leading and trailing whitespaces
        combined_name_query = (
            Concat('examination__patient__first_name', Value(' '),
                   'examination__patient__last_name', output_field=CharField())
        )
        return queryset.annotate(full_name=combined_name_query).filter(full_name__icontains=combined_name)

    def filter_doctor_name(self, queryset, name, value):
        combined_name = value.strip()  # Remove leading and trailing whitespaces
        combined_name_query = (
            Concat('examination__doctor_availability__doctor__first_name', Value(' '),
                   'examination__doctor_availability__doctor__last_name', output_field=CharField())
        )
        return queryset.annotate(full_name=combined_name_query).filter(full_name__icontains=combined_name)


class RecipientsFilter(django_filters.FilterSet):
    email = django_filters.CharFilter(field_name="email", lookup_expr="icontains")

    class Meta:
        model = User
        fields = ('email', )
