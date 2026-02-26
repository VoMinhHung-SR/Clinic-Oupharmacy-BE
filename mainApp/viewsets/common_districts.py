from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser, MultiPartParser

from mainApp.models import CommonDistrict
from mainApp.serializers import CommonDistrictSerializer
from mainApp.constant import LIMIT_LOCATION_LIST
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

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