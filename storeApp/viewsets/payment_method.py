from rest_framework import viewsets, generics
from storeApp.models import PaymentMethod
from storeApp.serializers import PaymentMethodSerializer


class PaymentMethodViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                            generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = PaymentMethod.objects.filter(active=True)
    serializer_class = PaymentMethodSerializer