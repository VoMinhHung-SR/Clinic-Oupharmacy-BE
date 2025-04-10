from django.contrib import admin

from django.utils.html import format_html
from django.shortcuts import render
from . import cloud_context
from django.urls import path
from django.utils.safestring import mark_safe
from .models import *
from django.template.response import TemplateResponse
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from datetime import date
from django.urls import reverse

from django_celery_beat.admin import ClockedScheduleAdmin, CrontabScheduleAdmin, \
    PeriodicTaskAdmin
from django_celery_beat.models import ClockedSchedule, \
    CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule

from django.contrib.auth import get_user_model

from oauth2_provider.models import (
    get_access_token_admin_class,
    get_access_token_model,
    get_application_admin_class,
    get_application_model,
    get_grant_admin_class,
    get_grant_model,
    get_id_token_admin_class,
    get_id_token_model,
    get_refresh_token_admin_class,
    get_refresh_token_model,
)

class MainAppAdminSite(admin.AdminSite):

    def index(self, request, extra_context=None):
        app_list = self.get_app_list(request)
        # Get counts of active patients, medicine units, and active users
        patients = Patient.objects.filter(active=True).count()
        medicine_units = MedicineUnit.objects.filter(active=True).count()
        users = User.objects.filter(is_active=True).count()

        # Get examination data
        examinations = Examination.objects.filter(created_date__year=date.today().year) \
            .annotate(month=TruncMonth('created_date')) \
            .values('month').annotate(count=Count('pk')).values('month', 'count')

        # Get bill data
        bills = Bill.objects.filter(created_date__year=date.today().year) \
            .annotate(month=TruncMonth('created_date')) \
            .values('month').annotate(total=Sum("amount"), count=Count("id")).values('month', 'total', 'count')

        # Get medicine data
        medicines = PrescriptionDetail.objects.filter(active=True) \
            .values('medicine_unit__medicine__name') \
            .annotate(count=Count('medicine_unit')) \
            .values('medicine_unit__medicine__name', 'count')

        # Prepare examination data for chart
        data_examination = [0] * 12
        for rs in examinations:
            month = rs['month'].month - 1
            data_examination[month] = rs['count']

        # Prepare revenue data for chart
        data_revenue = [0] * 12
        for rs in bills:
            month = rs['month'].month - 1
            data_revenue[month] = rs['total']

        # Prepare medicine data for chart
        data_medicine_labels = []
        data_medicine_quantity = []
        for m in medicines:
            data_medicine_labels.append(m['medicine_unit__medicine__name'])
            data_medicine_quantity.append(m['count'])

        context = {
            **self.each_context(request),
            "title": "OUPharmacy",
            "subtitle": None,
            "app_list": app_list,
            "patients": patients,
            "users": users,
            "data_examination": data_examination,
            "data_revenue": data_revenue,
            "current_year": date.today().year,
            "medicineUnits": medicine_units,
            'data_medicine_labels': data_medicine_labels,
            'data_medicine_quantity': data_medicine_quantity,
            **(extra_context or {}),
        }

        request.current_app = self.name

        return TemplateResponse(
            request, self.index_template or "admin/index.html", context
        )


admin_site = MainAppAdminSite(name='OUPharmacy')


class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'first_name', 'last_name', 'email', 'role']
    list_filter = ['email', 'role']
    search_fields = ['email']
    readonly_fields = ['avatar_view']

    def avatar_view(self, user):
        if user.avatar:
            return mark_safe(
                "<img src='{cloud_context}{url}' alt='avatar' width='200' />".format(cloud_context=cloud_context,
                                                                                     url=user.avatar)
            )


class PatientAdmin(admin.ModelAdmin):
    list_display = ['id', 'first_name', 'last_name', 'phone_number', 'email', 'gender']
    list_filter = ['last_name']

class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = ['id', 'doctor', 'date', 'session', 'is_off']
    list_filter = ['doctor', 'date', 'is_off']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "doctor":
            kwargs["queryset"] = User.objects.filter(role__name="ROLE_DOCTOR")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ['id', 'schedule', 'start_time', 'end_time', 'is_available']
    list_filter = ['schedule', 'is_available']

class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'active']


class ExaminationAdmin(admin.ModelAdmin):
    list_display = ['id', 'description', 'created_date', 'patient', 'time_slot']
    list_filter = ['patient', 'time_slot']


class MedicineAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'effect', 'contraindications', 'created_date']
    list_filter = ['name']


class MedicineUnitAdmin(admin.ModelAdmin):
    
    list_display = ['id', 'price', 'in_stock', 'created_date', 'packaging', 'medicine', 'category']
    list_filter = ['medicine', 'category']


class CategoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    list_filter = ['name']


class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ['id', 'sign', 'diagnosed', 'examination', 'user', 'patient']


class BillAdmin(admin.ModelAdmin):
    list_display = ['id', 'amount', 'prescribing']


class PrescribingAdmin(admin.ModelAdmin):
    list_display = ['id', 'diagnosis', 'user']


class PrescriptionDetailAdmin(admin.ModelAdmin):
    list_display = ['id', 'quantity', 'uses', 'prescribing', 'medicine_unit']


class MyModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'custom_field')

    def custom_field(self, obj):
        return format_html('<span>{}</span>', obj.field_name)

    custom_field.short_description = 'Custom Field'
    custom_field.allow_tags = True


def stats_view(request):
    return render(request, 'admin/stats.html', {})


class MyModelAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'stats_link']

    def stats_link(self, obj):
        url = reverse('admin:stats_view')
        return format_html('<a href="{}">Stats</a>', url)

    stats_link.short_description = 'Stats'


has_email = hasattr(get_user_model(), "email")


class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "client_type", "authorization_grant_type")
    list_filter = ("client_type", "authorization_grant_type", "skip_authorization")
    radio_fields = {
        "client_type": admin.HORIZONTAL,
        "authorization_grant_type": admin.VERTICAL,
    }
    search_fields = ("name",) + (("user__email",) if has_email else ())
    raw_id_fields = ("user",)


class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ("token", "user", "application", "expires")
    list_select_related = ("application", "user")
    raw_id_fields = ("user", "source_refresh_token")
    search_fields = ("token",) + (("user__email",) if has_email else ())
    list_filter = ("application",)


class GrantAdmin(admin.ModelAdmin):
    list_display = ("code", "application", "user", "expires")
    raw_id_fields = ("user",)
    search_fields = ("code",) + (("user__email",) if has_email else ())


class IDTokenAdmin(admin.ModelAdmin):
    list_display = ("jti", "user", "application", "expires")
    raw_id_fields = ("user",)
    search_fields = ("user__email",) if has_email else ()
    list_filter = ("application",)


class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ("token", "user", "application")
    raw_id_fields = ("user", "access_token")
    search_fields = ("token",) + (("user__email",) if has_email else ())
    list_filter = ("application",)


application_model = get_application_model()
access_token_model = get_access_token_model()
grant_model = get_grant_model()
id_token_model = get_id_token_model()
refresh_token_model = get_refresh_token_model()

application_admin_class = get_application_admin_class()
access_token_admin_class = get_access_token_admin_class()
grant_admin_class = get_grant_admin_class()
id_token_admin_class = get_id_token_admin_class()
refresh_token_admin_class = get_refresh_token_admin_class()

admin_site.register(application_model, application_admin_class)
admin_site.register(access_token_model, access_token_admin_class)
admin_site.register(grant_model, grant_admin_class)
admin_site.register(id_token_model, id_token_admin_class)
admin_site.register(refresh_token_model, refresh_token_admin_class)

admin_site.register(Bill, BillAdmin)
admin_site.register(Category, CategoryAdmin)
admin_site.register(Medicine, MedicineAdmin)
admin_site.register(MedicineUnit, MedicineUnitAdmin)
admin_site.register(Examination, ExaminationAdmin)
admin_site.register(Diagnosis, DiagnosisAdmin)
admin_site.register(Prescribing, PrescribingAdmin)
admin_site.register(PrescriptionDetail, PrescriptionDetailAdmin)
admin_site.register(Patient, PatientAdmin)
admin_site.register(User, UserAdmin)
admin_site.register(UserRole, UserRoleAdmin)
admin_site.register(DoctorSchedule, DoctorScheduleAdmin)
admin_site.register(TimeSlot, TimeSlotAdmin)

admin_site.register(IntervalSchedule)
admin_site.register(CrontabSchedule, CrontabScheduleAdmin)
admin_site.register(SolarSchedule)
admin_site.register(ClockedSchedule, ClockedScheduleAdmin)
admin_site.register(PeriodicTask, PeriodicTaskAdmin)
