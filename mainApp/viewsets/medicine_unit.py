from rest_framework import viewsets, generics, filters
from rest_framework.parsers import JSONParser, MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from mainApp.filters import MedicineUnitFilter, MedicineFilter
from django.db.models import Prefetch
from mainApp.models import MedicineUnit, Medicine
from mainApp.paginator import MedicineUnitPagination
from mainApp.serializers import MedicineUnitSerializer, MedicineWithUnitsSerializer

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters


class MedicineUnitViewSet(viewsets.ModelViewSet):

    queryset = MedicineUnit.objects.filter(active=True).select_related(
        "medicine",
        "category"
    ).order_by("medicine__name")

    serializer_class = MedicineUnitSerializer
    pagination_class = MedicineUnitPagination

    parser_classes = [JSONParser, MultiPartParser]

    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    ordering_fields = "__all__"

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return MedicineWithUnitsSerializer
        return MedicineUnitSerializer

    def get_filterset_class(self):
        if self.action in ["list", "retrieve"]:
            return MedicineFilter
        return MedicineUnitFilter

    def get_queryset(self):

        if self.action in ["list", "retrieve"]:

            units_qs = MedicineUnit.objects.filter(
                active=True
            ).select_related(
                "category"
            ).order_by(
                "package_size"
            )

            return Medicine.objects.filter(
                active=True,
                units__active=True
            ).prefetch_related(
                Prefetch(
                    "units",
                    queryset=units_qs
                )
            ).distinct().order_by("name")

        return super().get_queryset()

    def get_object(self):

        if self.action == "retrieve":

            units_qs = MedicineUnit.objects.filter(
                active=True
            ).select_related("category").order_by("package_size")

            return Medicine.objects.prefetch_related(
                Prefetch(
                    "units",
                    queryset=units_qs
                )
            ).get(
                id=self.kwargs["pk"],
                active=True
            )

        return super().get_object()