from rest_framework.serializers import ModelSerializer

from mainApp import cloud_context
from mainApp.models import User, UserRole

from rest_framework import serializers

class UserSerializer(ModelSerializer):

    def create(self, validated_data):
        user = User(**validated_data)
        print(validated_data.get('role'))
        user.set_password(user.password)
        user.save()

        return user

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            data['role'] = UserRole.objects.get(id=data['role']).name
        except:
            data['role'] = None
        return data

    locationGeo = serializers.SerializerMethodField(source="location")

    def get_locationGeo(self, obj):
        location = obj.location
        city = location.city
        district = location.district
        if location:
            return {'lat': location.lat, 'lng': location.lng,
                    'address': location.address,
                    'district': {'id': district.id, 'name': district.name},
                    'city': {'id': city.id, 'name': city.name}}
        else:
            return {}

    avatar_path = serializers.SerializerMethodField(source='avatar')

    def get_avatar_path(self, obj):
        if obj.avatar:
            path = "{cloud_context}{image_name}".format(cloud_context=cloud_context,
                                                        image_name=obj.avatar)
            return path

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "password",
                  "email", "phone_number", "date_of_birth", "locationGeo",
                  "date_joined", "gender", "avatar_path", "avatar", "is_admin", "role", "location"]
        extra_kwargs = {
            'password': {'write_only': 'true'},
            'avatar_path': {'read_only': 'true'},
            'locationGeo': {'read_only': 'true'},
            'avatar': {'write_only': 'true'},
            'location': {'write_only': 'true'}
        }