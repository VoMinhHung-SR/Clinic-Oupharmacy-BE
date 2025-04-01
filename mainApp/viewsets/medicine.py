from rest_framework import viewsets, generics

from mainApp.models import  Medicine
from mainApp.paginator import BasePagination
from mainApp.serializers import  MedicineSerializer

class MedicineViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                      generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = Medicine.objects.filter(active=True)
    serializer_class = MedicineSerializer
    pagination_class = BasePagination