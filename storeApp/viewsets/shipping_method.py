from rest_framework import viewsets, generics
from storeApp.models import ShippingMethod
from storeApp.serializers import ShippingMethodSerializer


class ShippingMethodViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                            generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = ShippingMethod.objects.filter(active=True)
    serializer_class = ShippingMethodSerializer