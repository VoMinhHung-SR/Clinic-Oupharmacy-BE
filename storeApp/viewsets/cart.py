from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from storeApp.models import Cart, CartItem, PaymentMethod, ShippingMethod, Voucher
from storeApp.serializers import CartSerializer, OrderSerializer
from storeApp.services.cart_cache import get_cart_cache_gateway
from storeApp.services.cart_service import (
    CartServiceError,
    CartVersionConflictError,
    add_or_update_item,
    checkout_cart,
    get_or_create_active_cart,
    recalculate_cart,
    remove_item,
    update_item,
)
from storeApp.services.voucher_engine import VoucherEngineError


class CartViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    CURRENT_CART_CACHE_TTL_SECONDS = 60

    def _active_cart(self, request):
        return get_or_create_active_cart(user_id=request.user.id, using="store")

    def _parse_expected_version(self, request):
        raw = request.data.get("expected_version")
        if raw is None:
            raw = request.query_params.get("expected_version")
        if raw is None:
            raise CartServiceError("expected_version is required")
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise CartServiceError("expected_version must be a valid integer")

    @action(methods=["get"], detail=False, url_path="current")
    def current(self, request):
        cart = self._active_cart(request)
        cache_gateway = get_cart_cache_gateway()
        try:
            cached_summary = cache_gateway.get_cart_summary(cart_id=cart.id)
            if cached_summary is not None:
                return Response(cached_summary)
        except Exception:
            # Cache is an optimization; request must still succeed on cache failures.
            pass

        cart = recalculate_cart(cart=cart, using="store", expected_version=cart.version)
        response_data = CartSerializer(cart).data
        try:
            cache_gateway.set_cart_summary(
                cart_id=cart.id,
                summary=response_data,
                ttl_seconds=self.CURRENT_CART_CACHE_TTL_SECONDS,
            )
        except Exception:
            pass
        return Response(response_data)

    @action(methods=["post"], detail=False, url_path="items")
    def add_item(self, request):
        cart = self._active_cart(request)
        try:
            expected_version = self._parse_expected_version(request)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
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
            cart = recalculate_cart(cart=cart, using="store", expected_version=expected_version)
        except (TypeError, ValueError):
            return Response({"error": "product_variant_id and quantity must be valid numbers"}, status=status.HTTP_400_BAD_REQUEST)
        except CartVersionConflictError as exc:
            return Response(
                {
                    "error": str(exc),
                    "details": {
                        "expected_version": exc.expected_version,
                        "current_version": exc.current_version,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

    @action(methods=["patch", "delete"], detail=False, url_path="items/(?P<item_id>[^/.]+)")
    def item_detail(self, request, item_id=None):
        cart = self._active_cart(request)
        try:
            expected_version = self._parse_expected_version(request)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if request.method.lower() == "patch":
                quantity_raw = request.data.get("quantity")
                unit_raw = request.data.get("product_variant_unit_id") or request.data.get("product_variant_unit")
                quantity = int(quantity_raw) if quantity_raw is not None else None
                product_variant_unit_id = int(unit_raw) if unit_raw is not None else None
                update_item(
                    cart=cart,
                    item_id=item_id,
                    quantity=quantity,
                    product_variant_unit_id=product_variant_unit_id,
                    using="store",
                )
            else:
                remove_item(cart=cart, item_id=item_id, using="store")
            cart = recalculate_cart(cart=cart, using="store", expected_version=expected_version)
        except CartItem.DoesNotExist:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)
        except (TypeError, ValueError):
            return Response(
                {"error": "quantity and product_variant_unit_id must be valid numbers"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CartVersionConflictError as exc:
            return Response(
                {
                    "error": str(exc),
                    "details": {
                        "expected_version": exc.expected_version,
                        "current_version": exc.current_version,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except CartServiceError as exc:
            status_code = status.HTTP_404_NOT_FOUND if request.method.lower() == "delete" else status.HTTP_400_BAD_REQUEST
            return Response({"error": str(exc)}, status=status_code)
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="select-shipping")
    def select_shipping(self, request):
        cart = self._active_cart(request)
        try:
            expected_version = self._parse_expected_version(request)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        shipping_method_id = request.data.get("shipping_method_id")
        try:
            shipping_method = ShippingMethod.objects.get(id=shipping_method_id, active=True)
        except ShippingMethod.DoesNotExist:
            return Response({"error": "ShippingMethod not found"}, status=status.HTTP_400_BAD_REQUEST)
        cart.shipping_method = shipping_method
        cart.save(update_fields=["shipping_method"])
        try:
            cart = recalculate_cart(cart=cart, using="store", expected_version=expected_version)
        except CartVersionConflictError as exc:
            return Response(
                {
                    "error": str(exc),
                    "details": {
                        "expected_version": exc.expected_version,
                        "current_version": exc.current_version,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="apply-voucher")
    def apply_voucher(self, request):
        cart = self._active_cart(request)
        try:
            expected_version = self._parse_expected_version(request)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
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
            cart = recalculate_cart(cart=cart, using="store", expected_version=expected_version)
        except Voucher.DoesNotExist:
            return Response({"error": "Voucher not found"}, status=status.HTTP_400_BAD_REQUEST)
        except CartVersionConflictError as exc:
            return Response(
                {
                    "error": str(exc),
                    "details": {
                        "expected_version": exc.expected_version,
                        "current_version": exc.current_version,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="remove-voucher")
    def remove_voucher(self, request):
        cart = self._active_cart(request)
        try:
            expected_version = self._parse_expected_version(request)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        target = request.data.get("target", "all")
        if target in ("order", "all"):
            cart.order_voucher = None
        if target in ("shipping", "all"):
            cart.shipping_voucher = None
        cart.save(update_fields=["order_voucher", "shipping_voucher"])
        cart = recalculate_cart(cart=cart, using="store", expected_version=expected_version)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="recalculate")
    def recalculate(self, request):
        cart = self._active_cart(request)
        try:
            expected_version = self._parse_expected_version(request)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cart = recalculate_cart(cart=cart, using="store", expected_version=expected_version)
        except CartVersionConflictError as exc:
            return Response(
                {
                    "error": str(exc),
                    "details": {
                        "expected_version": exc.expected_version,
                        "current_version": exc.current_version,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except VoucherEngineError as exc:
            return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CartSerializer(cart).data)

    @action(methods=["post"], detail=False, url_path="checkout")
    def checkout(self, request):
        cart = self._active_cart(request)
        try:
            expected_version = self._parse_expected_version(request)
        except CartServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payment_method_id = request.data.get("payment_method_id")
        shipping_address = request.data.get("shipping_address")
        notes = request.data.get("notes")
        raw_line_ids = request.data.get("cart_item_ids")
        checkout_item_ids = None
        if raw_line_ids is not None:
            if not isinstance(raw_line_ids, list):
                return Response({"error": "cart_item_ids must be a list or null"}, status=status.HTTP_400_BAD_REQUEST)
            if len(raw_line_ids) == 0:
                return Response({"error": "cart_item_ids cannot be empty"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                checkout_item_ids = [int(x) for x in raw_line_ids]
            except (TypeError, ValueError):
                return Response({"error": "cart_item_ids must be a list of integers"}, status=status.HTTP_400_BAD_REQUEST)
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
                expected_version=expected_version,
                checkout_item_ids=checkout_item_ids,
            )
        except PaymentMethod.DoesNotExist:
            return Response({"error": "PaymentMethod not found"}, status=status.HTTP_400_BAD_REQUEST)
        except CartVersionConflictError as exc:
            return Response(
                {
                    "error": str(exc),
                    "details": {
                        "expected_version": exc.expected_version,
                        "current_version": exc.current_version,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except (CartServiceError, VoucherEngineError) as exc:
            if isinstance(exc, VoucherEngineError):
                return Response({"error": "Validation failed", "details": exc.to_detail()}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
