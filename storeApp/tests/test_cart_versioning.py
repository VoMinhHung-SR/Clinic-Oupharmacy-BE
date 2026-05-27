"""Cart optimistic concurrency and cache read-through."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from unittest.mock import Mock, patch

from storeApp.models import (
    Category,
    MedicineBatch,
    PaymentMethod,
    Product,
    ProductVariant,
    ProductVariantUnit,
    ShippingMethod,
)

class CartVersioningFlowTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="cart-version-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.shipping_method = ShippingMethod.objects.create(
            name="Standard",
            price=30000,
            estimated_days=2,
            active=True,
        )
        self.payment_method = PaymentMethod.objects.create(
            name="COD",
            code="COD",
            active=True,
        )
        self.category = Category.objects.create(name="Thuốc tim", slug="thuoc-tim")
        self.product = Product.objects.create(
            name="Thuốc tim A",
            mid="MID-CART-001",
            slug="thuoc-tim-a",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp",
            in_stock=100,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=1,
            unit_name="Hộp",
            unit_order=0,
            price_value=100000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-CART-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=5),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=100,
            remaining_quantity=100,
        )

    def _current_cart(self):
        response = self.client.get("/api/store/carts/current/")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_add_item_requires_expected_version(self):
        response = self.client.post(
            "/api/store/carts/items/",
            {
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "expected_version is required")

    def test_mutate_cart_returns_409_when_expected_version_is_stale(self):
        cart_data = self._current_cart()
        old_version = cart_data["version"]

        add_response = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": old_version,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add_response.status_code, 200)
        new_version = add_response.data["version"]
        self.assertTrue(new_version > old_version)

        stale_response = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": old_version,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(stale_response.status_code, 409)
        self.assertEqual(stale_response.data["details"]["expected_version"], old_version)
        self.assertEqual(stale_response.data["details"]["current_version"], new_version)

    def test_order_create_with_cart_id_returns_409_on_stale_expected_version(self):
        cart_data = self._current_cart()
        cart_id = cart_data["id"]
        old_version = cart_data["version"]

        add_response = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": old_version,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add_response.status_code, 200)
        latest_version = add_response.data["version"]

        shipping_response = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": latest_version,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(shipping_response.status_code, 200)

        response = self.client.post(
            "/api/store/orders/",
            {
                "cart_id": cart_id,
                "expected_version": old_version,
                "payment_method_id": self.payment_method.id,
                "shipping_address": "123 stale version street",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["details"]["expected_version"], old_version)
        self.assertTrue(response.data["details"]["current_version"] > old_version)


class CartCurrentCacheReadThroughTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="cart-cache-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

    @patch("storeApp.viewsets.cart.recalculate_cart")
    @patch("storeApp.viewsets.cart.get_cart_cache_gateway")
    def test_current_returns_cached_summary_when_cache_hit(self, mock_get_gateway, mock_recalculate):
        cached_summary = {"id": 777, "source": "cache", "total": "123.00"}
        gateway = Mock()
        gateway.get_cart_summary.return_value = cached_summary
        mock_get_gateway.return_value = gateway

        response = self.client.get("/api/store/carts/current/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, cached_summary)
        mock_recalculate.assert_not_called()
        gateway.set_cart_summary.assert_not_called()

    @patch("storeApp.viewsets.cart.get_cart_cache_gateway")
    def test_current_sets_cache_when_cache_miss(self, mock_get_gateway):
        gateway = Mock()
        gateway.get_cart_summary.return_value = None
        mock_get_gateway.return_value = gateway

        response = self.client.get("/api/store/carts/current/")
        self.assertEqual(response.status_code, 200)
        gateway.get_cart_summary.assert_called_once()
        gateway.set_cart_summary.assert_called_once()

