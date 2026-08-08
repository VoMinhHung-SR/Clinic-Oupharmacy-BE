from rest_framework import viewsets, generics
from rest_framework.permissions import AllowAny
from mainApp.authz import is_business_admin
from mainApp.permissions import IsBusinessAdmin
from storeApp.models import ShippingMethod
from storeApp.serializers import ShippingMethodSerializer


class ShippingMethodViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                            generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = ShippingMethod.objects.all()
    serializer_class = ShippingMethodSerializer

    def get_queryset(self):
        if is_business_admin(self.request.user):
            return ShippingMethod.objects.all()
        return ShippingMethod.objects.filter(active=True)
    
    def get_permissions(self):
        """
        - list, retrieve: AllowAny
        - create, update, destroy: IsBusinessAdmin
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsBusinessAdmin]
        return [permission() for permission in permission_classes]