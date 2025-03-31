from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser, MultiPartParser

from mainApp.models import TimeSlot
from mainApp.serializers import TimeSlotSerializer

class TimeSlotViewSet(viewsets.ViewSet, generics.CreateAPIView,
                  generics.DestroyAPIView, generics.RetrieveAPIView,
                  generics.UpdateAPIView, generics.ListAPIView):
    queryset = TimeSlot.objects.all().order_by('-id')
    serializer_class = TimeSlotSerializer
    parser_classes = [JSONParser, MultiPartParser ]

