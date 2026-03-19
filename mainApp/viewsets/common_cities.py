from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import status
from mainApp.serializers import CommonCitySerializer, CommonDistrictSerializer
from mainApp.models import CommonCity, CommonDistrict

class CommonCityViewSet(viewsets.ViewSet):
    serializers = CommonCitySerializer

    @action(methods=['get'], detail=True, url_path='get-districts')
    def get_districts(self, request, pk):
        try:
            city = CommonCity.objects.get(id=pk)
            districts = CommonDistrict.objects.filter(city=city)
        except Exception as ex:
            return Response(data={"errMgs": "Cities not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data=CommonDistrictSerializer(districts, many=True).data, status=status.HTTP_200_OK)