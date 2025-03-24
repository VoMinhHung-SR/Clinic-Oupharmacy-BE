from django.urls import path, include
from . import views
from rest_framework import routers
from .admin import admin_site
from . import admin_views
from .services import statistic_views
from .viewsets import *

router = routers.DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("roles", UserRoleViewSet, basename="role")
router.register("categories", CategoryViewSet, basename="category")
router.register("examinations", ExaminationViewSet, basename="examination")
router.register("patients", PatientViewSet, basename="patient")
router.register("diagnosis", DiagnosisViewSet, basename="diagnosis")
router.register("prescribing", PrescribingViewSet, basename="prescribing")
router.register("prescription-details", PrescriptionDetailViewSet, basename="prescription-detail")
router.register("medicines", MedicineViewSet, basename="medicine")
router.register("medicine-units", MedicineUnitViewSet, basename="medicine-unit")
router.register("bills", BillViewSet, basename="bill")
router.register("common-districts", CommonDistrictViewSet, basename="common-districts")
router.register("common-locations", CommonLocationViewSet, basename="common-location")
router.register("doctor-schedules", DoctorScheduleViewSet, basename="doctor-schedule")
router.register("time-slots", TimeSlotViewSet, basename="time-slot")
urlpatterns = [
    path('', include(router.urls)),
    path('oauth2-info/', views.AuthInfo.as_view()),
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('admin/', include([
        path('api/revenue_stats/', admin_views.get_admin_revenue),
        path('api/examinations_stats/', admin_views.get_examinations_stats),
        path('api/medicines_stats/', admin_views.get_medicines_stats),
        path('api/doctor_stats/', admin_views.get_doctor_stats),
        path('',  admin_site.urls)
    ])),
    path('stats/', views.StatsView.as_view()),
    path('common-configs/', views.get_all_config),
    path('dashboard/stats/get-booking-stats/', statistic_views.get_booking_stats),
    path('dashboard/stats/get-medicine-stats/', statistic_views.get_medicines_stats),
    path('dashboard/stats/get-revenue-stats/', statistic_views.get_revenue_stats)
]
