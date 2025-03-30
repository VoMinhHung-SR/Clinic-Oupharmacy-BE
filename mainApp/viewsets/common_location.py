from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser, MultiPartParser

from mainApp.models import CommonDistrict, CommonLocation
from mainApp.serializers.common_location import CommonDistrictSerializer, CommonLocationSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

class CommonLocationViewSet(viewsets.ViewSet, generics.RetrieveAPIView, generics.ListAPIView,
                            generics.CreateAPIView, generics.DestroyAPIView, generics.UpdateAPIView):
    queryset = CommonLocation.objects.all()
    serializer_class = CommonLocationSerializer
    parser_classes = [JSONParser, MultiPartParser]

class CommonDistrictViewSet(viewsets.ViewSet):
    serializers = CommonDistrictSerializer

    @action(methods=['post'], detail=False, url_path='get-by-city')
    def get_by_city(self, request):
        try:
            districts = CommonDistrict.objects.filter(city_id=request.data.get('city')).all()
        except Exception as ex:
            return Response(data={"errMgs": "District have some errors"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data=CommonDistrictSerializer(districts, many=True).data,
                        status=status.HTTP_200_OK)