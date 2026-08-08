from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError

from django.utils.html import format_html
from django.shortcuts import redirect, render
from . import cloud_context
from django.urls import path
from django.utils.safestring import mark_safe
from django.utils import timezone
from .authz import is_business_admin, is_system_superadmin
from .models import *
from django.template.response import TemplateResponse
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from datetime import timedelta
from django.urls import reverse
from storeApp.models import ProductVariant, OrderItem, Order, MedicineBatch
import json


def _month_series(rows, value_key, year_len=12):
    data = [0] * year_len
    for rs in rows:
        month = rs.get("month")
        if not month:
            continue
        val = rs.get(value_key) or 0
        data[month.month - 1] = float(val) if value_key != "count" else int(val)
    return data


def _expiry_severity(days_left):
    if days_left < 0:
        return "expired"
    if days_left <= 7:
        return "urgent"
    if days_left <= 30:
        return "warning"
    return "watch"

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

class OUPharmacyAdminAuthenticationForm(AdminAuthenticationForm):
    """Allow is_superuser or is_admin (D-18). Do not require Django is_staff."""

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )
        if not is_business_admin(user):
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )


class MainAppAdminSite(admin.AdminSite):
    login_form = OUPharmacyAdminAuthenticationForm

    def has_permission(self, request):
        """Jazzmin: superuser (full site) or is_admin (Campaign-scoped via ModelAdmin)."""
        return is_business_admin(request.user)

    def index(self, request, extra_context=None):
        if is_business_admin(request.user) and not is_system_superadmin(request.user):
            return redirect(reverse(f"{self.name}:storeApp_campaign_changelist"))

        app_list = self.get_app_list(request)
        today = timezone.localdate()
        year = today.year
        try:
            expiry_days = int(request.GET.get("expiry_days", 30))
        except (TypeError, ValueError):
            expiry_days = 30
        if expiry_days not in (7, 30, 60, 90):
            expiry_days = 30

        patients = Patient.objects.filter(active=True).count()
        medicine_units = ProductVariant.objects.filter(active=True).count()
        users = User.objects.filter(is_active=True).count()

        exams_qs = Examination.objects.filter(created_date__year=year)
        exam_count_ytd = exams_qs.count()
        data_examination = _month_series(
            exams_qs.annotate(month=TruncMonth("created_date"))
            .values("month")
            .annotate(count=Count("pk")),
            "count",
        )
        status_rows = (
            exams_qs.values("status").annotate(count=Count("id")).order_by("status")
        )
        status_labels = [r["status"] or "unknown" for r in status_rows]
        status_counts = [r["count"] for r in status_rows]

        bills_qs = Bill.objects.filter(created_date__year=year)
        revenue_ytd = bills_qs.aggregate(total=Sum("amount"))["total"] or 0
        data_clinic_revenue = _month_series(
            bills_qs.annotate(month=TruncMonth("created_date"))
            .values("month")
            .annotate(total=Sum("amount")),
            "total",
        )

        orders_qs = Order.objects.filter(created_date__year=year)
        store_orders_ytd = orders_qs.count()
        store_revenue_ytd = orders_qs.aggregate(total=Sum("total"))["total"] or 0
        data_store_orders = _month_series(
            orders_qs.annotate(month=TruncMonth("created_date"))
            .values("month")
            .annotate(count=Count("pk")),
            "count",
        )
        data_store_revenue = _month_series(
            orders_qs.annotate(month=TruncMonth("created_date"))
            .values("month")
            .annotate(total=Sum("total")),
            "total",
        )
        order_status_rows = (
            orders_qs.values("status").annotate(count=Count("id")).order_by("status")
        )
        order_status_labels = [r["status"] or "unknown" for r in order_status_rows]
        order_status_counts = [r["count"] for r in order_status_rows]

        medicines = (
            OrderItem.objects.filter(active=True)
            .values("product_variant__product__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:8]
        )
        data_medicine_labels = [
            m["product_variant__product__name"] or "—" for m in medicines
        ]
        data_medicine_quantity = [m["count"] for m in medicines]

        stock_qs = MedicineBatch.objects.filter(active=True, remaining_quantity__gt=0)
        expired_stock = stock_qs.filter(expiry_date__lt=today).count()
        urgent_stock = stock_qs.filter(
            expiry_date__gte=today, expiry_date__lte=today + timedelta(days=7)
        ).count()
        warning_stock = stock_qs.filter(
            expiry_date__gt=today + timedelta(days=7),
            expiry_date__lte=today + timedelta(days=30),
        ).count()

        near_batches = list(
            MedicineBatch.objects.filter(
                active=True,
                remaining_quantity__gt=0,
                expiry_date__gte=today,
                expiry_date__lte=today + timedelta(days=expiry_days),
            )
            .select_related("product_variant", "product_variant__product")
            .order_by("expiry_date")[:40]
        )
        # Include expired with remaining stock when viewing ≤90 horizon
        expired_batches = list(
            MedicineBatch.objects.filter(
                active=True,
                remaining_quantity__gt=0,
                expiry_date__lt=today,
            )
            .select_related("product_variant", "product_variant__product")
            .order_by("expiry_date")[:15]
        )

        def _batch_url(pk):
            try:
                return reverse(
                    f"{self.name}:storeApp_medicinebatch_change", args=[pk]
                )
            except Exception:
                try:
                    return reverse("admin:storeApp_medicinebatch_change", args=[pk])
                except Exception:
                    return ""

        def _rows(batches, include_expired=False):
            rows = []
            for b in batches:
                days = b.days_until_expiry
                if not include_expired and days < 0:
                    continue
                pv = b.product_variant
                product_name = (
                    pv.product.name if pv and getattr(pv, "product", None) else "—"
                )
                rows.append(
                    {
                        "id": b.pk,
                        "batch_number": b.batch_number,
                        "product": product_name,
                        "sku": getattr(pv, "sku", "") or "—",
                        "packing": getattr(pv, "packing", "") or "—",
                        "expiry_date": b.expiry_date,
                        "days_left": days,
                        "remaining": b.remaining_quantity,
                        "severity": _expiry_severity(days),
                        "url": _batch_url(b.pk),
                    }
                )
            return rows

        near_expiry_rows = _rows(expired_batches, include_expired=True) + _rows(
            near_batches
        )
        # de-dupe by id, keep earliest expiry first
        seen = set()
        deduped = []
        for row in near_expiry_rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            deduped.append(row)
        near_expiry_rows = deduped[:50]

        try:
            batch_changelist_url = reverse(
                f"{self.name}:storeApp_medicinebatch_changelist"
            )
        except Exception:
            try:
                batch_changelist_url = reverse(
                    "admin:storeApp_medicinebatch_changelist"
                )
            except Exception:
                batch_changelist_url = "/admin/storeApp/medicinebatch/"

        context = {
            **self.each_context(request),
            "title": "Dashboard",
            "subtitle": None,
            "app_list": app_list,
            "patients": patients,
            "users": users,
            "exam_count_ytd": exam_count_ytd,
            "revenue_ytd": float(revenue_ytd),
            "store_orders_ytd": store_orders_ytd,
            "store_revenue_ytd": float(store_revenue_ytd),
            "current_year": year,
            "medicineUnits": medicine_units,
            "near_expiry_count": urgent_stock + warning_stock,
            "expired_stock_count": expired_stock,
            "expiry_days": expiry_days,
            "expiry_day_options": [7, 30, 60, 90],
            "near_expiry_rows": near_expiry_rows,
            "batch_changelist_url": batch_changelist_url,
            "chart_examination_json": mark_safe(json.dumps(data_examination)),
            "chart_clinic_revenue_json": mark_safe(json.dumps(data_clinic_revenue)),
            "chart_store_orders_json": mark_safe(json.dumps(data_store_orders)),
            "chart_store_revenue_json": mark_safe(json.dumps(data_store_revenue)),
            "chart_status_labels_json": mark_safe(json.dumps(status_labels)),
            "chart_status_counts_json": mark_safe(json.dumps(status_counts)),
            "chart_order_status_labels_json": mark_safe(
                json.dumps(order_status_labels)
            ),
            "chart_order_status_counts_json": mark_safe(
                json.dumps(order_status_counts)
            ),
            "chart_medicine_labels_json": mark_safe(json.dumps(data_medicine_labels)),
            "chart_medicine_quantity_json": mark_safe(
                json.dumps(data_medicine_quantity)
            ),
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
    
    def save_model(self, request, obj, form, change):
        if obj.password:
            obj.set_password(obj.password)
        
        if hasattr(obj.avatar, 'read'):
            import cloudinary.uploader
            upload_result = cloudinary.uploader.upload(obj.avatar)
            obj.avatar = upload_result['public_id']
        elif not obj.avatar:
            from .constant import CLOUDINARY_DEFAULT_AVATAR
            obj.avatar = CLOUDINARY_DEFAULT_AVATAR
        
        super().save_model(request, obj, form, change)

    def avatar_view(self, user):
        if user.avatar:
            return mark_safe(
                "<img src='{cloud_context}{url}' alt='avatar' width='200' />".format(cloud_context=cloud_context,
                                                                                     url=user.avatar)
            )

class PatientAdmin(admin.ModelAdmin):
    list_display = ['id', 'first_name', 'last_name', 'phone_number', 'email', 'gender', 'allergies']
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


class UserAddressAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'address_short', 'is_default', 'created_date']
    list_filter = ['user', 'is_default']
    search_fields = ['address', 'user__email']
    raw_id_fields = ['user', 'city', 'district']

    def address_short(self, obj):
        return (obj.address[:50] + '...') if obj.address and len(obj.address) > 50 else (obj.address or '')
    address_short.short_description = 'Address'


class ExaminationAdmin(admin.ModelAdmin):
    list_display = ['id', 'description', 'status', 'mail_status', 'created_date', 'patient', 'time_slot']
    list_filter = ['status', 'mail_status', 'patient', 'time_slot']


class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ['id', 'sign', 'diagnosed', 'examination', 'user', 'patient', 'active']


class BillAdmin(admin.ModelAdmin):
    list_display = ['id', 'amount', 'status', 'paid_at', 'prescribing']
    list_filter = ['status']


class PrescribingAdmin(admin.ModelAdmin):
    list_display = ['id', 'diagnosis', 'user', 'active']


class PrescriptionDetailAdmin(admin.ModelAdmin):
    # Store-driven fields; legacy `medicine_unit` is no longer required at runtime.
    list_display = ['id','quantity','uses','prescribing','product_variant_id','product_variant_unit_id']

class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'description', 'get_specializations']
    list_filter = ['user', 'specializations']

    def get_specializations(self, obj):
        return ", ".join([tag.name for tag in obj.specializations.all()])

    get_specializations.short_description = "Specializations"

class SpecializationTagAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']

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
admin_site.register(Examination, ExaminationAdmin)
admin_site.register(Diagnosis, DiagnosisAdmin)
admin_site.register(Prescribing, PrescribingAdmin)
admin_site.register(PrescriptionDetail, PrescriptionDetailAdmin)
admin_site.register(Patient, PatientAdmin)
admin_site.register(User, UserAdmin)
admin_site.register(UserAddress, UserAddressAdmin)
admin_site.register(UserRole, UserRoleAdmin)
admin_site.register(DoctorSchedule, DoctorScheduleAdmin)
admin_site.register(DoctorProfile, DoctorProfileAdmin)
admin_site.register(SpecializationTag, SpecializationTagAdmin)
admin_site.register(TimeSlot, TimeSlotAdmin)

admin_site.register(IntervalSchedule)
admin_site.register(CrontabSchedule, CrontabScheduleAdmin)
admin_site.register(SolarSchedule)
admin_site.register(ClockedSchedule, ClockedScheduleAdmin)
admin_site.register(PeriodicTask, PeriodicTaskAdmin)
