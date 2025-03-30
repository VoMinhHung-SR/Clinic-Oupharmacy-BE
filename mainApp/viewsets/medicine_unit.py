from rest_framework import viewsets, generics, filters
from rest_framework.parsers import JSONParser, MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from mainApp.filters import MedicineUnitFilter
from mainApp.models import MedicineUnit
from mainApp.paginator import MedicineUnitPagination
from mainApp.serializers.medicine_unit import MedicineUnitSerializer

class MedicineUnitViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                          generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = MedicineUnit.objects.filter(active=True).order_by('medicine__name')
    serializer_class = MedicineUnitSerializer
    pagination_class = MedicineUnitPagination
    parser_classes = [JSONParser, MultiPartParser]
    ordering_fields = '__all__'
    filterset_class = MedicineUnitFilter
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]