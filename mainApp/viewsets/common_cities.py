from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from mainApp.models import CommonCity, CommonDistrict


class CommonCityViewSet(viewsets.ViewSet):
    """Reference data: provinces/cities (CommonCity) and wards/communes (CommonDistrict)."""

    permission_classes = [AllowAny]
    pagination_class = None

    def list(self, request):
        rows = CommonCity.objects.order_by("name").values("id", "name", "id_province")
        return Response(list(rows), status=status.HTTP_200_OK)

    @action(methods=["get"], detail=True, url_path="get-districts")
    def get_districts(self, request, pk):
        try:
            pk_int = int(pk)
        except (TypeError, ValueError):
            return Response(data={"detail": "Invalid city id"}, status=status.HTTP_400_BAD_REQUEST)
        if not CommonCity.objects.filter(id=pk_int).exists():
            return Response(data={"detail": "City not found"}, status=status.HTTP_404_NOT_FOUND)
        districts = (
            CommonDistrict.objects.filter(city_id=pk_int)
            .order_by("name")
            .values("id", "name", "id_commune", "city_id")
        )
        return Response(list(districts), status=status.HTTP_200_OK)