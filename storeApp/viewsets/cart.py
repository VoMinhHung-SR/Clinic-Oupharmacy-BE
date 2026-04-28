from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from storeApp.models import Cart, CartItem, PaymentMethod, ShippingMethod, Voucher
from storeApp.serializers import CartSerializer, OrderSerializer
from storeApp.services.cart_service import (
    CartServiceError,
    add_or_update_item,
    checkout_cart,
    get_or_create_active_cart,
    recalculate_cart,
    remove_item,
)
from storeApp.services.voucher_engine import VoucherEngineError


class CartViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _active_cart(self, request):
        return get_or_create_active_cart(user_id=request.user.id, using="store")

    @action(methods=["get"], detail=False, url_path="current")
    def current(self, request):
        cart = self._active_cart(request)
        cart = recalculate_cart(cart=cart, using="store")
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="items")
    def add_item(self, request):
        cart = self._active_cart(request)
        product_variant_id = request.data.get("product_variant_id") or request.data.get("product_variant")
        product_variant_unit_id = request.data.get("product_variant_unit_id") or request.data.get("product_variant_unit")
        quantity = request.data.get("quantity")
        try:
            add_or_update_item(
                cart=cart,
                product_variant_id=int(product_variant_id),
                product_variant_unit_id=int(product_variant_unit_id) if product_variant_unit_id else None,
                quantity=int(quantity),
                using="store",
            )
            cart = recalculate_cart(cart=cart, using="store")
        except (TypeError, ValueError):
            return Response({"error": "product_variant_id and quantity must be valid numbers"}, status=status.HTTP_400_BAD_REQUEST)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

    @action(methods=["patch"], detail=False, url_path="items/(?P<item_id>[^/.]+)")
    def update_item(self, request, item_id=None):
        cart = self._active_cart(request)
        quantity = request.data.get("quantity")
        try:
            item = cart.items.get(id=item_id)
            add_or_update_item(
                cart=cart,
                product_variant_id=item.product_variant_id,
                product_variant_unit_id=item.product_variant_unit_id,
                quantity=int(quantity),
                using="store",
            )
            cart = recalculate_cart(cart=cart, using="store")
        except CartItem.DoesNotExist:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)
        except (TypeError, ValueError):
            return Response({"error": "quantity must be a valid number"}, status=status.HTTP_400_BAD_REQUEST)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data)

    @action(methods=["delete"], detail=False, url_path="items/(?P<item_id>[^/.]+)")
    def delete_item(self, request, item_id=None):
        cart = self._active_cart(request)
        try:
            remove_item(cart=cart, item_id=item_id, using="store")
            cart = recalculate_cart(cart=cart, using="store")
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="select-shipping")
    def select_shipping(self, request):
        cart = self._active_cart(request)
        shipping_method_id = request.data.get("shipping_method_id")
        try:
            shipping_method = ShippingMethod.objects.get(id=shipping_method_id, active=True)
        except ShippingMethod.DoesNotExist:
            return Response({"error": "ShippingMethod not found"}, status=status.HTTP_400_BAD_REQUEST)
        cart.shipping_method = shipping_method
        cart.save(update_fields=["shipping_method"])
        try:
            cart = recalculate_cart(cart=cart, using="store")
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="apply-voucher")
    def apply_voucher(self, request):
        cart = self._active_cart(request)
        order_voucher_code = (request.data.get("order_voucher_code") or "").strip()
        shipping_voucher_code = (request.data.get("shipping_voucher_code") or "").strip()
        if not order_voucher_code and not shipping_voucher_code:
            return Response({"error": "At least one voucher code is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if order_voucher_code:
                cart.order_voucher = Voucher.objects.get(code=order_voucher_code)
            if shipping_voucher_code:
                cart.shipping_voucher = Voucher.objects.get(code=shipping_voucher_code)
            cart.save(update_fields=["order_voucher", "shipping_voucher"])
            cart = recalculate_cart(cart=cart, using="store")
        except Voucher.DoesNotExist:
            return Response({"error": "Voucher not found"}, status=status.HTTP_400_BAD_REQUEST)
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="remove-voucher")
    def remove_voucher(self, request):
        cart = self._active_cart(request)
        target = request.data.get("target", "all")
        if target in ("order", "all"):
            cart.order_voucher = None
        if target in ("shipping", "all"):
            cart.shipping_voucher = None
        cart.save(update_fields=["order_voucher", "shipping_voucher"])
        cart = recalculate_cart(cart=cart, using="store")
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="recalculate")
    def recalculate(self, request):
        cart = self._active_cart(request)
        try:
            cart = recalculate_cart(cart=cart, using="store")
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="checkout")
    def checkout(self, request):
        cart = self._active_cart(request)
        payment_method_id = request.data.get("payment_method_id")
        shipping_address = request.data.get("shipping_address")
        notes = request.data.get("notes")
        if not payment_method_id:
            return Response({"error": "payment_method_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not shipping_address:
            return Response({"error": "shipping_address is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment_method = PaymentMethod.objects.get(id=payment_method_id, active=True)
            order = checkout_cart(
                cart=cart,
                payment_method=payment_method,
                shipping_address=shipping_address,
                notes=notes,
                using="store",
            )
        except PaymentMethod.DoesNotExist:
            return Response({"error": "PaymentMethod not found"}, status=status.HTTP_400_BAD_REQUEST)
        except (CartServiceError, VoucherEngineError) as exc:
            if isinstance(exc, VoucherEngineError):
                return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
