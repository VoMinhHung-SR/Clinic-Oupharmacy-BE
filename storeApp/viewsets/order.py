from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.db import transaction, models
from django.utils import timezone
from storeApp.models import Order, OrderItem, MedicineBatch, ShippingMethod, PaymentMethod
from storeApp.serializers import OrderSerializer, OrderItemSerializer
from mainApp.models import MedicineUnit


class OrderViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                   generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        - list, retrieve: AllowAny (public)
        - create: IsAuthenticated (user)
        - update, destroy: IsAdminUser (admin)
        - by_user: IsAuthenticated (user)
        - update_status: IsAdminUser (admin)
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        elif self.action in ['create', 'by_user']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def _validate_order_item(self, item_data, idx):
        """Validate một order item"""
        medicine_unit_id = item_data.get('medicine_unit_id')
        quantity = item_data.get('quantity')
        price = item_data.get('price')
        
        # Validate required fields
        if not medicine_unit_id:
            return {'item_index': idx, 'field': 'medicine_unit_id', 'error': 'medicine_unit_id is required'}
        if not quantity or quantity <= 0:
            return {'item_index': idx, 'field': 'quantity', 'error': 'quantity must be greater than 0'}
        if not price or price < 0:
            return {'item_index': idx, 'field': 'price', 'error': 'price must be greater than or equal to 0'}
        
        # Validate MedicineUnit exists and active
        try:
            medicine_unit = MedicineUnit.objects.using('default').get(id=medicine_unit_id, active=True)
        except MedicineUnit.DoesNotExist:
            return {'item_index': idx, 'medicine_unit_id': medicine_unit_id, 'error': 'MedicineUnit not found or inactive'}
        
        # Validate price
        if abs(float(price) - float(medicine_unit.price)) > 0.01:
            return {
                'item_index': idx,
                'medicine_unit_id': medicine_unit_id,
                'field': 'price',
                'error': f'Price mismatch. Expected: {medicine_unit.price}, Got: {price}'
            }
        
        # Validate stock availability
        today = timezone.now().date()
        total_available = MedicineBatch.objects.filter(
            medicine_unit_id=medicine_unit_id,
            active=True,
            remaining_quantity__gt=0,
            expiry_date__gte=today
        ).aggregate(total=models.Sum('remaining_quantity'))['total'] or 0
        
        if total_available < quantity:
            return {
                'item_index': idx,
                'medicine_unit_id': medicine_unit_id,
                'field': 'quantity',
                'error': f'Insufficient stock. Available: {total_available}, Requested: {quantity}'
            }
        
        return None
    
    def _deduct_stock(self, medicine_unit_id, quantity):
        """Trừ tồn kho theo FIFO"""
        today = timezone.now().date()
        available_batches = MedicineBatch.objects.filter(
            medicine_unit_id=medicine_unit_id,
            active=True,
            remaining_quantity__gt=0,
            expiry_date__gte=today
        ).order_by('expiry_date', 'import_date')
        
        remaining = quantity
        for batch in available_batches:
            if remaining <= 0:
                break
            
            if batch.remaining_quantity >= remaining:
                batch.remaining_quantity -= remaining
                batch.save(update_fields=['remaining_quantity'])
                remaining = 0
            else:
                remaining -= batch.remaining_quantity
                batch.remaining_quantity = 0
                batch.save(update_fields=['remaining_quantity'])
        
        if remaining > 0:
            raise ValueError(f'Insufficient stock for medicine_unit_id {medicine_unit_id}. Could not deduct {remaining} units.')
    
    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        items_data = data.pop('items', [])
        
        if not items_data:
            return Response(
                {'error': 'Order must have at least one item'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate tất cả items
        validation_errors = [
            error for idx, item_data in enumerate(items_data)
            if (error := self._validate_order_item(item_data, idx)) is not None
        ]
        
        if validation_errors:
            return Response(
                {'error': 'Validation failed', 'details': validation_errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate và lấy shipping_method, payment_method
        shipping_method_obj = None
        payment_method_obj = None
        
        if 'shipping_method_id' in data:
            try:
                shipping_method_obj = ShippingMethod.objects.get(id=data.pop('shipping_method_id'))
            except ShippingMethod.DoesNotExist:
                return Response(
                    {'error': 'ShippingMethod not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if 'payment_method_id' in data:
            try:
                payment_method_obj = PaymentMethod.objects.get(id=data.pop('payment_method_id'))
            except PaymentMethod.DoesNotExist:
                return Response(
                    {'error': 'PaymentMethod not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Create order and items in transaction
        with transaction.atomic(using='store'):
            serializer = self.get_serializer(data=data)
            if shipping_method_obj:
                serializer._shipping_method = shipping_method_obj
            if payment_method_obj:
                serializer._payment_method = payment_method_obj
            
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
            
            # Create order items and deduct stock
            for item_data in items_data:
                OrderItem.objects.create(order=order, **item_data)
                self._deduct_stock(
                    item_data['medicine_unit_id'],
                    item_data['quantity']
                )
        
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
        """
        Get list of orders by user_id.
        Only allow users to view their own orders, or admin can view all.
        """
        # Check if user is viewing their own orders or admin
        if request.user.is_authenticated:
            if str(request.user.id) != str(user_id) and not request.user.is_staff:
                return Response(
                    {'error': 'You can only view your own orders'},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        orders = Order.objects.filter(user_id=user_id).order_by('-created_date')
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)