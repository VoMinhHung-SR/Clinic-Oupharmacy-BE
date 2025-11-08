from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from storeApp.models import Order, OrderItem
from storeApp.serializers import OrderSerializer, OrderItemSerializer


class OrderViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                   generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    def create(self, request, *args, **kwargs):
        """Tạo order với items"""
        items_data = request.data.pop('items', [])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        
        # Tạo order items
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        
        headers = self.get_success_headers(serializer.data)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(methods=['post'], detail=True, url_path='update-status')
    def update_status(self, request, pk=None):
        """Cập nhật trạng thái đơn hàng"""
        order = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(Order.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = new_status
        order.save()
        return Response(OrderSerializer(order).data)
    
    @action(methods=['get'], detail=False, url_path='by-user/(?P<user_id>[^/.]+)')
    def by_user(self, request, user_id=None):
        """Lấy danh sách đơn hàng theo user_id"""
        orders = Order.objects.filter(user_id=user_id)
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)