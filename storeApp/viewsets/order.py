from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.db import transaction
from django.utils import timezone
from storeApp.models import Order, OrderItem, MedicineBatch
from storeApp.serializers import OrderSerializer, OrderItemSerializer
from mainApp.models import MedicineUnit


class OrderViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                   generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    # def get_permissions(self):
    #     """
    #     Instantiates and returns the list of permissions that this view requires.
    #     - list, retrieve: AllowAny (public)
    #     - create: IsAuthenticated (user)
    #     - update, destroy: IsAdminUser (admin)
    #     - by_user: IsAuthenticated (user)
    #     - update_status: IsAdminUser (admin)
    #     """
    #     if self.action in ['list', 'retrieve']:
    #         permission_classes = [AllowAny]
    #     elif self.action in ['create', 'by_user']:
    #         permission_classes = [IsAuthenticated]
    #     else:
    #         permission_classes = [IsAdminUser]
    #     return [permission() for permission in permission_classes]
    
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
            
            if abs(float(price) - float(medicine_unit.price)) > 0.01:
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
        
        # Sử dụng database 'store' cho transaction vì Order và MedicineBatch đều ở store database
        with transaction.atomic(using='store'):
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
            
            # Tạo order items và trừ tồn kho theo FIFO (First In First Out)
            for item_data in items_data:
                medicine_unit_id = item_data.get('medicine_unit_id')
                quantity = item_data.get('quantity')
                
                # Tạo order item
                OrderItem.objects.create(order=order, **item_data)
                
                # Trừ tồn kho theo FIFO (ưu tiên lô sắp hết hạn trước)
                remaining_quantity = quantity
                today = timezone.now().date()
                
                # Lấy các batches còn hàng, chưa hết hạn, sắp xếp theo expiry_date (FIFO)
                available_batches = MedicineBatch.objects.filter(
                    medicine_unit_id=medicine_unit_id,
                    active=True,
                    remaining_quantity__gt=0,
                    expiry_date__gte=today
                ).order_by('expiry_date', 'import_date')
                
                # Trừ tồn kho từ các batches theo thứ tự
                for batch in available_batches:
                    if remaining_quantity <= 0:
                        break
                    
                    if batch.remaining_quantity >= remaining_quantity:
                        # Batch này đủ để trừ hết số lượng còn lại
                        batch.remaining_quantity -= remaining_quantity
                        batch.save(update_fields=['remaining_quantity'])
                        remaining_quantity = 0
                    else:
                        # Batch này không đủ, trừ hết batch này và tiếp tục batch tiếp theo
                        remaining_quantity -= batch.remaining_quantity
                        batch.remaining_quantity = 0
                        batch.save(update_fields=['remaining_quantity'])
                
                # Kiểm tra nếu vẫn còn quantity chưa trừ (không nên xảy ra vì đã validate)
                if remaining_quantity > 0:
                    # Rollback transaction nếu có lỗi
                    raise ValueError(
                        f'Insufficient stock for medicine_unit_id {medicine_unit_id}. '
                        f'Could not deduct {remaining_quantity} units.'
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
        # Kiểm tra nếu user đang xem đơn hàng của chính mình hoặc là admin
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