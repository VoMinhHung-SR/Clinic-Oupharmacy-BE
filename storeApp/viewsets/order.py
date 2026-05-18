from decimal import Decimal, InvalidOperation

from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.serializers import ValidationError as DRFValidationError
from rest_framework.generics import get_object_or_404
from django.db import transaction, IntegrityError
from storeApp.models import (
    Order,
    OrderItem,
    Cart,
    ShippingMethod,
    PaymentMethod,
    ProductVariant,
    ProductVariantUnit,
)
from storeApp.serializers import OrderSerializer
from storeApp.services.stock import get_available_stock, deduct_stock, restore_stock
from storeApp.services.voucher_engine import (
    VoucherEngineError,
    consume_vouchers,
    resolve_voucher_discounts,
)
from storeApp.services.cart_service import CartServiceError, CartVersionConflictError, checkout_cart
from storeApp.services.checkout_delivery import resolve_checkout_shipping_address

class OrderViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                   generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Order.objects.select_related(
        'shipping_method',
        'payment_method',
        'order_voucher',
        'shipping_voucher',
    ).all()
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
        product_variant_unit_id = item_data.get('product_variant_unit') or item_data.get('product_variant_unit_id')
        quantity = item_data.get('quantity')
        price = item_data.get('price')
        
        # Validate required fields
        if not product_variant_id:
            return {'item_index': idx, 'field': 'product_variant', 'error': 'product_variant is required'}
        if not quantity or quantity <= 0:
            return {'item_index': idx, 'field': 'quantity', 'error': 'quantity must be greater than 0'}
        if price is None:
            return {'item_index': idx, 'field': 'price', 'error': 'price is required'}
        try:
            price_decimal = Decimal(str(price))
        except (InvalidOperation, TypeError):
            return {'item_index': idx, 'field': 'price', 'error': 'price must be a valid decimal'}
        if price_decimal < 0:
            return {'item_index': idx, 'field': 'price', 'error': 'price must be greater than or equal to 0'}
        
        # Validate ProductVariant exists and active
        try:
            product_variant = ProductVariant.objects.select_related('product__category').get(
                id=product_variant_id,
                active=True,
            )
        except ProductVariant.DoesNotExist:
            return {'item_index': idx, 'product_variant': product_variant_id, 'error': 'ProductVariant not found or inactive'}

        if product_variant_unit_id:
            try:
                product_variant_unit = ProductVariantUnit.objects.get(
                    id=product_variant_unit_id,
                    variant_id=product_variant.id,
                    is_published=True,
                )
            except ProductVariantUnit.DoesNotExist:
                return {
                    'item_index': idx,
                    'product_variant': product_variant_id,
                    'field': 'product_variant_unit',
                    'error': 'ProductVariantUnit not found for this variant',
                }
        else:
            product_variant_unit = ProductVariantUnit.objects.filter(
                variant_id=product_variant.id,
                is_default=True,
                is_published=True,
            ).first() or ProductVariantUnit.objects.filter(
                variant_id=product_variant.id,
                is_published=True,
            ).order_by('unit_order', 'id').first()
            if not product_variant_unit:
                return {
                    'item_index': idx,
                    'product_variant': product_variant_id,
                    'field': 'product_variant_unit',
                    'error': 'No published ProductVariantUnit for this variant',
                }

        # Validate price theo ProductVariantUnit (đơn vị bán được chọn)
        expected_price = Decimal(str(product_variant_unit.price_value))
        if abs(float(price_decimal - expected_price)) > 0.01:
            return {
                'item_index': idx,
                'product_variant': product_variant_id,
                'field': 'price',
                'error': f'Price mismatch. Expected: {expected_price}, Got: {price}'
            }

        # Validate stock theo đơn vị cơ sở (quantity order * quantity_in_base)
        required_base_quantity = int(quantity) * int(product_variant_unit.quantity_in_base)
        total_available = get_available_stock(product_variant_id)
        if total_available < required_base_quantity:
            return {
                'item_index': idx,
                'product_variant': product_variant_id,
                'field': 'quantity',
                'error': (
                    f'Insufficient stock in base unit. '
                    f'Available: {total_available}, Requested: {required_base_quantity}'
                ),
            }

        return {
            'item_index': idx,
            'product_variant': product_variant,
            'product_variant_unit': product_variant_unit,
            'quantity': int(quantity),
            'price': price_decimal,
            'required_base_quantity': required_base_quantity,
        }
    
    def _deduct_stock(self, product_variant_id, quantity):
        """Trừ tồn kho qua stock service (FIFO trên batches + sync cache)."""
        deduct_stock(product_variant_id, quantity)

    def _restore_stock(self, order):
        """Hoàn tồn kho khi đơn bị hủy: gọi restore_stock cho từng item (LIFO/ADJ + sync cache)."""
        for item in order.items.all():
            quantity_in_base = item.product_variant_unit.quantity_in_base if item.product_variant_unit else 1
            restore_stock(item.product_variant_id, item.quantity * quantity_in_base)

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        cart_id = data.get("cart_id")
        if cart_id:
            payment_id = data.get("payment_method_id") or data.get("payment_method")
            expected_version_raw = data.get("expected_version")
            shipping_address_raw = data.get("shipping_address")
            delivery_raw = data.get("delivery")
            notes = data.get("notes")
            if payment_id is None:
                return Response(
                    {'error': 'payment_method or payment_method_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            shipping_address, delivery_errors = resolve_checkout_shipping_address(
                shipping_address=shipping_address_raw,
                delivery=delivery_raw,
            )
            if delivery_errors is not None:
                return Response(
                    {'error': 'Validation failed', 'details': delivery_errors},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not shipping_address:
                return Response(
                    {'error': 'shipping_address is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                payment_method_obj = PaymentMethod.objects.get(id=payment_id, active=True)
            except (PaymentMethod.DoesNotExist, TypeError, ValueError):
                return Response(
                    {'error': 'PaymentMethod not found', 'payment_method_id': payment_id},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                cart = Cart.objects.select_related(
                    "shipping_method", "order_voucher", "shipping_voucher"
                ).get(id=cart_id, user_id=request.user.id)
            except Cart.DoesNotExist:
                return Response(
                    {'error': 'Cart not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            try:
                expected_version = int(expected_version_raw) if expected_version_raw is not None else int(cart.version)
            except (TypeError, ValueError):
                return Response(
                    {'error': 'expected_version must be a valid integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                order = checkout_cart(
                    cart=cart,
                    payment_method=payment_method_obj,
                    shipping_address=shipping_address,
                    notes=notes,
                    using='store',
                    expected_version=expected_version,
                )
            except CartVersionConflictError as exc:
                return Response(
                    {
                        'error': str(exc),
                        'details': {
                            'expected_version': exc.expected_version,
                            'current_version': exc.current_version,
                        },
                    },
                    status=status.HTTP_409_CONFLICT
                )
            except (CartServiceError, VoucherEngineError) as exc:
                if isinstance(exc, VoucherEngineError):
                    return Response(
                        {'error': 'Validation failed', 'details': exc.to_detail()},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                return Response(
                    {'error': str(exc)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            response_serializer = self.get_serializer(order)
            headers = self.get_success_headers(response_serializer.data)
            headers["X-Checkout-Flow"] = "cart"
            return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

        raw_items = data.pop('items', [])
        order_voucher_code = (data.pop('order_voucher_code', None) or '').strip()
        shipping_voucher_code = (data.pop('shipping_voucher_code', None) or '').strip()
        items_data = raw_items if isinstance(raw_items, list) else ([raw_items] if raw_items else [])
        
        if not items_data:
            return Response(
                {'error': 'Order must have at least one item'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate tất cả items
        validation_errors = []
        normalized_items = []
        for idx, item_data in enumerate(items_data):
            result = self._validate_order_item(item_data, idx)
            if result and result.get('error'):
                validation_errors.append(result)
            else:
                normalized_items.append(result)

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
        
        order_subtotal = Decimal('0')
        for item_data in normalized_items:
            order_subtotal += item_data['price'] * item_data['quantity']
        shipping_fee_base = Decimal(str(shipping_method_obj.price))

        product_mids = set()
        category_slugs = set()
        for item_data in normalized_items:
            product = item_data['product_variant'].product
            if product and product.mid:
                product_mids.add(str(product.mid))
            category = getattr(product, 'category', None)
            if category and category.slug:
                category_slugs.add(str(category.slug))

        # Create order and items in transaction
        try:
            with transaction.atomic(using='store'):
                user_id = request.user.id if request.user and request.user.is_authenticated else None
                voucher_result = resolve_voucher_discounts(
                    order_voucher_code=order_voucher_code,
                    shipping_voucher_code=shipping_voucher_code,
                    order_subtotal=order_subtotal,
                    shipping_fee_base=shipping_fee_base,
                    product_mids=product_mids,
                    category_slugs=category_slugs,
                    user_id=user_id,
                    using='store',
                )

                serializer = self.get_serializer(data=data)
                serializer._shipping_method = shipping_method_obj
                serializer._payment_method = payment_method_obj
                serializer._computed_order_fields = {
                    'subtotal': order_subtotal,
                    'shipping_fee': voucher_result['final_shipping_fee'],
                    'total': voucher_result['final_total'],
                    'order_voucher': voucher_result['order_voucher'],
                    'shipping_voucher': voucher_result['shipping_voucher'],
                    'discount_amount': voucher_result['order_discount_amount'],
                    'shipping_discount_amount': voucher_result['shipping_discount_amount'],
                }
                serializer.is_valid(raise_exception=True)
                order = serializer.save()
                # Create order items and deduct stock
                for item_data in normalized_items:
                    OrderItem.objects.create(
                        order=order,
                        product_variant=item_data['product_variant'],
                        product_variant_unit=item_data['product_variant_unit'],
                        quantity=item_data['quantity'],
                        price=item_data['price'],
                    )
                    self._deduct_stock(
                        item_data['product_variant'].id,
                        item_data['required_base_quantity'],
                    )
                consume_vouchers(
                    order=order,
                    user_id=user_id,
                    order_voucher=voucher_result['order_voucher'],
                    shipping_voucher=voucher_result['shipping_voucher'],
                    order_discount_amount=voucher_result['order_discount_amount'],
                    shipping_discount_amount=voucher_result['shipping_discount_amount'],
                    using='store',
                )
        except DRFValidationError as e:
            return Response(
                {'error': 'Validation failed', 'details': e.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        except VoucherEngineError as e:
            return Response(
                {'error': 'Validation failed', 'details': e.to_detail()},
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
        
        response_serializer = self.get_serializer(order)
        headers = self.get_success_headers(response_serializer.data)
        headers["X-Checkout-Flow"] = "legacy-order-create"
        headers["X-Checkout-Deprecation"] = "Use /api/store/carts/checkout/ as primary flow"
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
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