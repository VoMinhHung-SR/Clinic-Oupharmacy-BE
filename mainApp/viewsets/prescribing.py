from rest_framework import viewsets, generics
from django.db import transaction
from mainApp.models import  Prescribing, PrescriptionDetail
from mainApp.paginator import ExaminationPaginator
from mainApp.serializers import PrescribingSerializer
from mainApp.serializers import PrescriptionDetailSerializer
from mainApp.models import Diagnosis
from mainApp.services.diagnosis_medicine_suggestions import get_diagnosis_medicine_suggestions
from mainApp.services.prescriber_medicine_prefs import get_prescriber_medicine_prefs
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

class PrescribingViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                         generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = Prescribing.objects.filter(active=True)
    serializer_class = PrescribingSerializer
    pagination_class = ExaminationPaginator

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        diagnosis = serializer.validated_data.get('diagnosis')
        with transaction.atomic():
            if diagnosis is not None:
                Prescribing.objects.filter(diagnosis=diagnosis, active=True).update(active=False)
            self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(methods=['POST'], detail=False, url_path='get-by-diagnosis')
    def get_by_diagnosis(self, request):
        user = request.user
        if user:
            try:
                prescribing = Prescribing.objects.filter(
                    diagnosis=request.data.get('diagnosis'),
                    active=True,
                ).all()
            except:
                return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            if prescribing:
                return Response(data=PrescribingSerializer(prescribing, many=True,
                                context={'request': request}).data,
                                status=status.HTTP_200_OK)
            return Response(status=status.HTTP_200_OK, data=[])
        return Response(data={"errMgs": "User not found"},
                        status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True, url_path='get-pres-detail')
    def get_prescription_detail(self, request, pk):
        prescription_detail = PrescriptionDetail.objects.filter(prescribing=pk).all()

        return Response(data=PrescriptionDetailSerializer(prescription_detail, many=True,
                                                          context={'request': request}).data,
                        status=status.HTTP_200_OK)

    @action(methods=['get'], detail=False, url_path='medicine-prefs')
    def medicine_prefs(self, request):
        user = request.user
        if not user or not getattr(user, 'is_authenticated', False):
            return Response(
                data={"errMgs": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(
            data=get_prescriber_medicine_prefs(user.id),
            status=status.HTTP_200_OK,
        )

    @action(methods=['get'], detail=False, url_path='medicine-suggestions')
    def medicine_suggestions(self, request):
        user = request.user
        if not user or not getattr(user, 'is_authenticated', False):
            return Response(
                data={"errMgs": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        diagnosis_id = request.query_params.get('diagnosis_id')
        if not diagnosis_id:
            return Response(
                data={"errMgs": "diagnosis_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            diagnosis_id_int = int(diagnosis_id)
        except (TypeError, ValueError):
            return Response(
                data={"errMgs": "diagnosis_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = get_diagnosis_medicine_suggestions(diagnosis_id_int, user.id)
        except Diagnosis.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(data=data, status=status.HTTP_200_OK)
