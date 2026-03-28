from rest_framework import viewsets, generics
from rest_framework.permissions import AllowAny, IsAdminUser
from storeApp.models import PaymentMethod
from storeApp.serializers import PaymentMethodSerializer


class PaymentMethodViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                           generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializer

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return PaymentMethod.objects.all()
        return PaymentMethod.objects.filter(active=True)
    
    def get_permissions(self):
        """
        - list, retrieve: AllowAny
        - create, update, destroy: IsAdminUser (admin)
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]