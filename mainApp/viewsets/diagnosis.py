from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser, MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from mainApp.filters import DiagnosisFilter
from mainApp.models import Diagnosis
from mainApp.paginator import ExaminationPaginator
from mainApp.serializers import DiagnosisSerializer, DiagnosisCRUDSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, filters

class DiagnosisViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                       generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = Diagnosis.objects.filter(active=True).order_by('-created_date')
    serializer_class = DiagnosisSerializer
    parser_classes = [JSONParser, MultiPartParser]
    pagination_class = ExaminationPaginator
    ordering_fields = '__all__'
    filterset_class = DiagnosisFilter
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]

    def create(self, request, *args, **kwargs):
        serializer = DiagnosisCRUDSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(methods=['POST'], detail=False, url_path='get-medical-records')
    def get_patient_medical_records(self, request):
        try:
            medical_records = Diagnosis.objects.filter(patient=int(request.data.get('patientId'))).all()\
                .order_by('-created_date')
        except Exception as ex:
            print(ex)
            return Response(data={"errMgs": "Can not get patient's medical records"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        if medical_records:
            return Response(data=DiagnosisSerializer(medical_records, context={'request': request}, many=True).data,
                            status=status.HTTP_200_OK)
        return Response(data=[], status=status.HTTP_200_OK)
