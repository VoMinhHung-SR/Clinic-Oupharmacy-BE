from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser, MultiPartParser
from mainApp.models import PrescriptionDetail
from mainApp.serializers.prescribing_detail import PrescriptionDetailCRUDSerializer

class PrescriptionDetailViewSet(viewsets.ViewSet, generics.RetrieveAPIView,
                                generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = PrescriptionDetail.objects.filter(active=True)
    serializer_class = PrescriptionDetailCRUDSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def get_parsers(self):
        if getattr(self, 'swagger_fake_view', False):
            return []

        return super().get_parsers()
