from rest_framework import viewsets, generics
from rest_framework.permissions import AllowAny, IsAdminUser
from storeApp.models import Brand
from storeApp.serializers import BrandSerializer


class BrandViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                   generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Brand.objects.filter(active=True)
    serializer_class = BrandSerializer
    
    def get_permissions(self):
        """
        - list, retrieve: AllowAny (public)
        - create, update, destroy: IsAdminUser (admin)
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]