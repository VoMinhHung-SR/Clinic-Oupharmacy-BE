from rest_framework import viewsets, generics
from mainApp.models import  Prescribing, PrescriptionDetail
from mainApp.paginator import ExaminationPaginator
from mainApp.serializers.prescribing import PrescribingSerializer
from mainApp.serializers.prescribing_detail import PrescriptionDetailSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

class PrescribingViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                         generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = Prescribing.objects.filter(active=True)
    serializer_class = PrescribingSerializer
    pagination_class = ExaminationPaginator

    @action(methods=['POST'], detail=False, url_path='get-by-diagnosis')
    def get_by_diagnosis(self, request):
        user = request.user
        if user:
            try:
                prescribing = Prescribing.objects.filter(diagnosis=request.data.get('diagnosis')).all()
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
