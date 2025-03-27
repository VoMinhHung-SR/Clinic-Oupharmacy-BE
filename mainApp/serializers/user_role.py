from rest_framework.serializers import ModelSerializer

from mainApp.models import UserRole


class UserRoleSerializer(ModelSerializer):
    class Meta:
        model = UserRole
        exclude = ['active']