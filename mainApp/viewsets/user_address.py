from rest_framework import viewsets, generics, permissions, status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from mainApp.models import UserAddress
from mainApp.serializers import UserAddressSerializer


class UserAddressViewSet(viewsets.ViewSet, generics.ListCreateAPIView,
                         generics.RetrieveAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    serializer_class = UserAddressSerializer
    parser_classes = [JSONParser, MultiPartParser]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return UserAddress.objects.none()
        return UserAddress.objects.filter(user=self.request.user).order_by('-is_default', 'id')

    def perform_create(self, serializer):
        serializer.save()
