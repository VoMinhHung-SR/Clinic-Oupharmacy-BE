from rest_framework import viewsets, generics, filters
from rest_framework.parsers import JSONParser, MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from mainApp.filters import MedicineUnitFilter, MedicineFilter
from mainApp.models import MedicineUnit, Medicine
from mainApp.paginator import MedicineUnitPagination
from mainApp.serializers import MedicineUnitSerializer, MedicineWithUnitsSerializer

class MedicineUnitViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                          generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = MedicineUnit.objects.filter(active=True).select_related('medicine', 'category').order_by('medicine__name')
    serializer_class = MedicineUnitSerializer
    pagination_class = MedicineUnitPagination
    parser_classes = [JSONParser, MultiPartParser]
    ordering_fields = '__all__'
    filterset_class = MedicineUnitFilter
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]

    def get_filterset_class(self):
        if self.action in ['list', 'retrieve']:
            return MedicineFilter
        return MedicineUnitFilter

    def get_queryset(self):
        if self.action in ['list', 'retrieve']:
            return Medicine.objects.filter(
                units__active=True,
                active=True
            ).select_related().prefetch_related('units').distinct().order_by('name')
        return super().get_queryset()

    def get_object(self):
        if self.action == 'retrieve':
            medicine_id = self.kwargs.get('pk')
            return Medicine.objects.filter(
                id=medicine_id,
                units__active=True,
                active=True
            ).select_related().prefetch_related('units').distinct().get()
        return super().get_object()

    