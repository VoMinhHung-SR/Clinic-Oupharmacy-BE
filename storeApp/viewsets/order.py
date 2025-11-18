from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from storeApp.models import Order, OrderItem, MedicineBatch
from storeApp.serializers import OrderSerializer, OrderItemSerializer
from mainApp.models import MedicineUnit


class OrderViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                   generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        items_data = data.pop('items', [])
        
        if not items_data:
            return Response(
                {'error': 'Order must have at least one item'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validation_errors = []
        
        for idx, item_data in enumerate(items_data):
            medicine_unit_id = item_data.get('medicine_unit_id')
            quantity = item_data.get('quantity')
            price = item_data.get('price')
            
            if not medicine_unit_id:
                validation_errors.append({
                    'item_index': idx,
                    'field': 'medicine_unit_id',
                    'error': 'medicine_unit_id is required'
                })
                continue
            
            if not quantity or quantity <= 0:
                validation_errors.append({
                    'item_index': idx,
                    'field': 'quantity',
                    'error': 'quantity must be greater than 0'
                })
                continue
            
            if not price or price < 0:
                validation_errors.append({
                    'item_index': idx,
                    'field': 'price',
                    'error': 'price must be greater than or equal to 0'
                })
                continue
            
            try:
                medicine_unit = MedicineUnit.objects.using('default').get(
                    id=medicine_unit_id,
                    active=True
                )
            except MedicineUnit.DoesNotExist:
                validation_errors.append({
                    'item_index': idx,
                    'medicine_unit_id': medicine_unit_id,
                    'error': 'MedicineUnit not found or inactive'
                })
                continue
            
            if abs(float(price) - float(medicine_unit.price)) > 0.01:  # Cho phép sai số nhỏ do float
                validation_errors.append({
                    'item_index': idx,
                    'medicine_unit_id': medicine_unit_id,
                    'field': 'price',
                    'error': f'Price mismatch. Expected: {medicine_unit.price}, Got: {price}'
                })
                continue
            
            today = timezone.now().date()
            available_batches = MedicineBatch.objects.filter(
                medicine_unit_id=medicine_unit_id,
                active=True,
                remaining_quantity__gt=0,
                expiry_date__gte=today
            ).order_by('expiry_date', 'import_date')
            
            total_available_quantity = sum(
                batch.remaining_quantity for batch in available_batches
            )
            
            if total_available_quantity < quantity:
                validation_errors.append({
                    'item_index': idx,
                    'medicine_unit_id': medicine_unit_id,
                    'field': 'quantity',
                    'error': f'Insufficient stock. Available: {total_available_quantity}, Requested: {quantity}'
                })
                continue
        
        if validation_errors:
            return Response(
                {
                    'error': 'Validation failed',
                    'details': validation_errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
            
            for item_data in items_data:
                OrderItem.objects.create(order=order, **item_data)
        
        headers = self.get_success_headers(serializer.data)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(methods=['post'], detail=True, url_path='update-status')
    def update_status(self, request, pk=None):
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
        orders = Order.objects.filter(user_id=user_id)
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)