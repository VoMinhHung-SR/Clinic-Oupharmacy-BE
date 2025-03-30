from rest_framework import viewsets, generics
from mainApp.models import UserRole
from mainApp.serializers.user_role import UserRoleSerializer
class UserRoleViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                      generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = UserRole.objects.filter(active=True)
    serializer_class = UserRoleSerializer