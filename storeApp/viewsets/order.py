from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.serializers import ValidationError as DRFValidationError
from rest_framework.generics import get_object_or_404
from django.db import transaction, IntegrityError
from storeApp.models import Order, OrderItem, ShippingMethod, PaymentMethod, ProductVariant
from storeApp.serializers import OrderSerializer

class OrderViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                   generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def get_permissions(self):
        """
        - list: IsAdminUser (only admin sees all orders)
        - retrieve: IsAuthenticated (owner or admin only, enforced via get_queryset)
        - create, by_user: IsAuthenticated
        - update, destroy, update_status: IsAdminUser
        """
        if self.action == 'list':
            permission_classes = [IsAdminUser]
        elif self.action in ['retrieve', 'create', 'by_user', 'cancel']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """Restrict list to admin; restrict retrieve to owner or admin."""
        if self.action == 'list':
            if self.request.user.is_authenticated and self.request.user.is_staff:
                return Order.objects.all()
            return Order.objects.none()
        if self.action == 'retrieve':
            if self.request.user.is_authenticated and self.request.user.is_staff:
                return Order.objects.all()
            if self.request.user.is_authenticated:
                return Order.objects.filter(user_id=self.request.user.id)
            return Order.objects.none()
        if self.action == 'cancel':
            if self.request.user.is_authenticated:
                return Order.objects.filter(user_id=self.request.user.id)
            return Order.objects.none()
        if self.action in ['update_status']:
            if self.request.user.is_authenticated and self.request.user.is_staff:
                return Order.objects.all()
            return Order.objects.none()
        return Order.objects.all()

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        pk = self.kwargs.get('pk')
        if pk is None:
            raise AssertionError('Expected pk in URL kwargs')
        if str(pk).isdigit():
            return get_object_or_404(queryset, id=int(pk))
        return get_object_or_404(queryset, order_number=pk)

    def _validate_order_item(self, item_data, idx):
        """Validate một order item"""
        product_variant_id = item_data.get('product_variant') or item_data.get('product_variant_id')
        quantity = item_data.get('quantity')
        price = item_data.get('price')
        
        # Validate required fields
        if not product_variant_id:
            return {'item_index': idx, 'field': 'product_variant', 'error': 'product_variant is required'}
        if not quantity or quantity <= 0:
            return {'item_index': idx, 'field': 'quantity', 'error': 'quantity must be greater than 0'}
        if not price or price < 0:
            return {'item_index': idx, 'field': 'price', 'error': 'price must be greater than or equal to 0'}
        
        # Validate ProductVariant exists and active
        try:
            product_variant = ProductVariant.objects.get(id=product_variant_id, active=True)
        except ProductVariant.DoesNotExist:
            return {'item_index': idx, 'product_variant': product_variant_id, 'error': 'ProductVariant not found or inactive'}
        
        # Validate price (ProductVariant has price_value)
        expected_price = product_variant.price_value
        if abs(float(price) - float(expected_price)) > 0.01:
            return {
                'item_index': idx,
                'product_variant': product_variant_id,
                'field': 'price',
                'error': f'Price mismatch. Expected: {expected_price}, Got: {price}'
            }
        
        # Validate stock availability (single source of truth: batches via stock service)
        total_available = get_available_stock(product_variant_id)
        if total_available < quantity:
            return {
                'item_index': idx,
                'product_variant': product_variant_id,
                'field': 'quantity',
                'error': f'Insufficient stock. Available: {total_available}, Requested: {quantity}'
            }
        
        return None
    
    def _deduct_stock(self, product_variant_id, quantity):
        """Trừ tồn kho qua stock service (FIFO trên batches + sync cache)."""
        deduct_stock(product_variant_id, quantity)

    def _restore_stock(self, order):
        """Hoàn tồn kho khi đơn bị hủy: gọi restore_stock cho từng item (LIFO/ADJ + sync cache)."""
        for item in order.items.all():
            restore_stock(item.product_variant_id, item.quantity)
    
    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        raw_items = data.pop('items', [])
        items_data = raw_items if isinstance(raw_items, list) else ([raw_items] if raw_items else [])
        
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
        
        shipping_id = data.pop('shipping_method_id', None) or data.pop('shipping_method', None)
        payment_id = data.pop('payment_method_id', None) or data.pop('payment_method', None)
        
        if shipping_id is None:
            return Response(
                {'error': 'shipping_method or shipping_method_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if payment_id is None:
            return Response(
                {'error': 'payment_method or payment_method_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            shipping_method_obj = ShippingMethod.objects.get(id=shipping_id)
        except (ShippingMethod.DoesNotExist, TypeError, ValueError):
            return Response(
                {'error': 'ShippingMethod not found', 'shipping_method_id': shipping_id},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            payment_method_obj = PaymentMethod.objects.get(id=payment_id)
        except (PaymentMethod.DoesNotExist, TypeError, ValueError):
            return Response(
                {'error': 'PaymentMethod not found', 'payment_method_id': payment_id},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create order and items in transaction
        try:
            with transaction.atomic(using='store'):
                serializer = self.get_serializer(data=data)
                serializer._shipping_method = shipping_method_obj
                serializer._payment_method = payment_method_obj
                serializer.is_valid(raise_exception=True)
                order = serializer.save()
                # Create order items and deduct stock
                for item_data in items_data:
                    from storeApp.models import ProductVariant # inline import to avoid circular dep
                    # handle both product_variant and product_variant_id
                    pv_id = item_data.pop('product_variant', None) or item_data.pop('product_variant_id', None)
                    if pv_id:
                        try:
                            pv = ProductVariant.objects.get(id=pv_id)
                            item_data['product_variant'] = pv
                        except ProductVariant.DoesNotExist:
                            pass
                    OrderItem.objects.create(order=order, **item_data)
                    self._deduct_stock(
                        pv_id,
                        item_data['quantity']
                    )
        except DRFValidationError as e:
            return Response(
                {'error': 'Validation failed', 'details': e.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        except IntegrityError as e:
            return Response(
                {'error': 'Invalid data', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
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
        if new_status == Order.CANCELLED:
            with transaction.atomic(using='store'):
                self._restore_stock(order)
                order.status = new_status
                order.save(update_fields=['status'])
        else:
            order.status = new_status
            order.save(update_fields=['status'])
        return Response(OrderSerializer(order).data)

    @action(methods=['post'], detail=True, url_path='cancel')
    def cancel(self, request, pk=None):
        """User hủy đơn (chỉ đơn PENDING, chỉ chủ đơn)."""
        order = self.get_object()
        if order.user_id != request.user.id:
            return Response(
                {'error': 'You can only cancel your own order'},
                status=status.HTTP_403_FORBIDDEN
            )
        if order.status != Order.PENDING:
            return Response(
                {'error': 'Only PENDING orders can be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic(using='store'):
            self._restore_stock(order)
            order.status = Order.CANCELLED
            order.save(update_fields=['status'])
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