from rest_framework import viewsets, generics

from mainApp.models import SpecializationTag
from mainApp.serializers import SpecializationTagSerializer


class SpecializationTagViewSet(viewsets.ViewSet, generics.ListAPIView, generics.UpdateAPIView,
                      generics.CreateAPIView, generics.DestroyAPIView):
    queryset = SpecializationTag.objects.filter(active=True)
    serializer_class = SpecializationTagSerializer
