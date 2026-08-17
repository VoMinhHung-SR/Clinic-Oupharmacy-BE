from rest_framework import viewsets, generics
from mainApp.permissions import IsBusinessAdmin
from storeApp.models import MedicineBatch
from storeApp.serializers import MedicineBatchSerializer


class MedicineBatchViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                           generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = MedicineBatch.objects.all()
    serializer_class = MedicineBatchSerializer
    permission_classes = [IsBusinessAdmin]