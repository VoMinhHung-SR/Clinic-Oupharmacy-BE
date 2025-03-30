from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser, MultiPartParser

from mainApp.models import Patient
from mainApp.paginator import BasePagination
from mainApp.serializers.patient import PatientSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

class PatientViewSet(viewsets.ViewSet, generics.ListAPIView, generics.CreateAPIView,
                     generics.RetrieveAPIView, generics.UpdateAPIView):
    queryset = Patient.objects.filter(active=True)
    serializer_class = PatientSerializer
    pagination_class = BasePagination
    parser_classes = [JSONParser, MultiPartParser, ]

    @action(methods=['post'], detail=False, url_path='get-patient-by-email')
    def get_patient_by_email(self, request):
        user = request.user
        if user:
            try:
                email = request.data.get('email')
            except:
                return Response(status=status.HTTP_400_BAD_REQUEST)
            if email:
                try:
                    patient = Patient.objects.get(email=email)
                except Patient.DoesNotExist:
                    return Response(data={"patient": None},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                return Response(PatientSerializer(patient, context={'request': request}).data,
                                status=status.HTTP_200_OK)
            return Response(status=status.HTTP_400_BAD_REQUEST)
        return Response(data={"errMgs": "User not found"},
                        status=status.HTTP_400_BAD_REQUEST)
