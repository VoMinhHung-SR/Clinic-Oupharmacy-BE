from rest_framework.serializers import ModelSerializer

from mainApp.models import CommonCity, CommonDistrict, CommonLocation
from rest_framework import serializers

class CommonCitySerializer(ModelSerializer):
    class Meta:
        model = CommonCity
        fields = ["id", "name"]

class CommonDistrictSerializer(ModelSerializer):
    city = CommonCitySerializer()

    class Meta:
        model = CommonDistrict
        fields = ["id", "name", "city"]

class CommonLocationSerializer(ModelSerializer):
    district_info = serializers.SerializerMethodField(source='district')
    city_info = serializers.SerializerMethodField(source='city')

    def get_district_info(self, obj):
        district = obj.district
        if district:
            return {'id': district.id, 'name': district.name}
        else:
            return {}

    def get_city_info(self, obj):
        city = obj.city
        if city:
            return {'id': city.id, 'name': city.name}
        else:
            return {}

    class Meta:
        model = CommonLocation
        fields = ["id", "address", "lat", "lng", "city", 'district', "district_info", "city_info"]
        extra_kwargs = {
            'city': {'write_only': 'true'},
            'city_info': {'read_only': 'true'},
            'district_info': {'read_only': 'true'},
            'district': {'write_only': 'true'}
        }