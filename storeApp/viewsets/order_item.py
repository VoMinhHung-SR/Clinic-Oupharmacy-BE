from rest_framework import viewsets, generics
from rest_framework.permissions import IsAdminUser
from storeApp.models import OrderItem
from storeApp.serializers import OrderItemSerializer


class OrderItemViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                       generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [IsAdminUser]