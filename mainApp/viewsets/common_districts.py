

# TODO: refactor this API to get all districts; 
# now using get-districts API in CommonCityViewSet

# class CommonDistrictViewSet(viewsets.ViewSet):
#     serializers = CommonDistrictSerializer

#     @action(methods=['post'], detail=True, url_path='get-by-city')
#     def get_by_city(self, request):
#         try:
#             districts = CommonDistrict.objects.filter(city_id=request.data.get('city')).all()
#         except Exception as ex:
#             return Response(data={"errMgs": "District have some errors"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#         return Response(data=CommonDistrictSerializer(districts, many=True).data,
#                         status=status.HTTP_200_OK)