"""Cart checkout flows: delivery payload, guest cart, free shipping."""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APITestCase

from storeApp.models import (
    Cart,
    Category,
    MedicineBatch,
    Order,
    PaymentMethod,
    Product,
    ProductVariant,
    ProductVariantUnit,
    ShippingMethod,
)

class CartCheckoutDeliveryApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="checkout-delivery-user@example.com",
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
        self.category = Category.objects.create(name="Thuốc ho", slug="thuoc-ho")
        self.product = Product.objects.create(
            name="Thuốc ho A",
            mid="MID-CHK-DLV-001",
            slug="thuoc-ho-a",
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
            price_value=50000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-CHK-DLV-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=5),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=100,
            remaining_quantity=100,
        )

    def _delivery_body(self):
        return {
            "orderer": {"name": "Đặt Hàng", "phone": "0382590839", "email": "orderer@example.com"},
            "recipient": {"name": "Nhận Hàng", "phone": "0382590839"},
            "address": {"province": "HN", "district": "Ba Đình", "ward": "P1", "detail": "12 Phố Huế"},
        }

    def test_carts_checkout_accepts_delivery_object(self):
        cart_data = self.client.get("/api/store/carts/current/").data
        v0 = cart_data["version"]

        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        v1 = add.data["version"]

        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": v1,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        v2 = ship.data["version"]

        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": v2,
                "payment_method_id": self.payment_method.id,
                "delivery": self._delivery_body(),
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        self.assertIn("Người đặt:", checkout.data["shipping_address"])
        self.assertIn("Người nhận:", checkout.data["shipping_address"])
        order = Order.objects.filter(user_id=self.user.id).order_by("-id").first()
        self.assertIsNotNone(order)
        self.assertIn("Email người đặt:", order.shipping_address)

    def test_carts_checkout_delivery_validation_error(self):
        cart_data = self.client.get("/api/store/carts/current/").data
        v0 = cart_data["version"]

        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        v1 = add.data["version"]

        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": v1,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        v2 = ship.data["version"]

        bad_delivery = {
            "orderer": {"name": "A", "phone": "invalid"},
            "recipient": {"name": "B", "phone": "0382590839"},
            "address": {"detail": "12 Phố Huế"},
        }
        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": v2,
                "payment_method_id": self.payment_method.id,
                "delivery": bad_delivery,
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 400)
        self.assertEqual(checkout.data.get("error"), "Validation failed")

    def test_carts_checkout_insufficient_stock_returns_400_not_500(self):
        cart_data = self.client.get("/api/store/carts/current/").data
        v0 = cart_data["version"]

        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 2,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        v1 = add.data["version"]

        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": v1,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        v2 = ship.data["version"]

        MedicineBatch.objects.filter(product_variant_id=self.variant.id).update(remaining_quantity=1)

        orders_before = Order.objects.filter(user_id=self.user.id).count()
        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": v2,
                "payment_method_id": self.payment_method.id,
                "delivery": self._delivery_body(),
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 400, checkout.data)
        self.assertIn("Insufficient stock", checkout.data.get("error", ""))
        self.assertEqual(Order.objects.filter(user_id=self.user.id).count(), orders_before)


class GuestCartCheckoutTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.guest_session_id = str(uuid.uuid4())
        self.client.credentials(HTTP_X_GUEST_SESSION=self.guest_session_id)

        self.shipping_method = ShippingMethod.objects.create(
            name="Guest Standard",
            price=25000,
            estimated_days=2,
            active=True,
        )
        self.payment_method = PaymentMethod.objects.create(
            name="Guest COD",
            code="GUEST_COD",
            active=True,
        )
        self.category = Category.objects.create(name="Guest Cat", slug="guest-cat")
        self.product = Product.objects.create(
            name="Guest Product A",
            mid="MID-GUEST-001",
            slug="guest-product-a",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp",
            in_stock=50,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=1,
            unit_name="Hộp",
            unit_order=0,
            price_value=80000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-GUEST-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=3),
            expiry_date=timezone.now().date() + timedelta(days=200),
            quantity=50,
            remaining_quantity=50,
        )

    def _delivery_body(self):
        return {
            "orderer": {"name": "Khách Lẻ", "phone": "0901234567", "email": "guest@example.com"},
            "recipient": {"name": "Khách Lẻ", "phone": "0901234567"},
            "address": {"province": "HN", "district": "Cầu Giấy", "ward": "Dịch Vọng", "detail": "1 Guest St"},
        }

    def test_guest_cart_current_without_header_is_forbidden(self):
        anon = self.client_class()()
        response = anon.get("/api/store/carts/current/")
        self.assertIn(response.status_code, (401, 403))

    def test_guest_cart_add_and_checkout_creates_order_without_user(self):
        current = self.client.get("/api/store/carts/current/")
        self.assertEqual(current.status_code, 200)
        self.assertIsNone(current.data.get("user_id"))
        self.assertEqual(str(current.data.get("guest_session_id")), self.guest_session_id)
        v0 = current.data["version"]

        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        v1 = add.data["version"]

        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": v1,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        v2 = ship.data["version"]

        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": v2,
                "payment_method_id": self.payment_method.id,
                "delivery": self._delivery_body(),
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        order = Order.objects.get(order_number=checkout.data["order_number"])
        self.assertIsNone(order.user_id)
        self.assertIn("Người nhận:", order.shipping_address)

    def test_merge_guest_cart_into_user_on_login(self):
        current = self.client.get("/api/store/carts/current/").data
        v0 = current["version"]
        self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 2,
            },
            format="json",
        )

        user_model = get_user_model()
        user = user_model.objects.create_user(
            email="guest-merge-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=user)
        merge = self.client.post("/api/store/carts/merge-guest/", {}, format="json")
        self.assertEqual(merge.status_code, 200)
        self.assertEqual(merge.data["items"][0]["quantity"], 2)
        guest_cart = Cart.objects.filter(guest_session_id=self.guest_session_id, status=Cart.ABANDONED).first()
        self.assertIsNotNone(guest_cart)


class StoreConstantsUnitTests(SimpleTestCase):
    def test_free_shipping_threshold_default(self):
        from storeApp.services.store_constants import (
            FREE_SHIPPING_ORDER_SUBTOTAL,
            apply_free_shipping_base,
            qualifies_for_free_shipping,
        )

        self.assertEqual(FREE_SHIPPING_ORDER_SUBTOTAL, Decimal("300000"))
        self.assertTrue(qualifies_for_free_shipping(Decimal("300000")))
        self.assertFalse(qualifies_for_free_shipping(Decimal("299999.99")))
        base = Decimal("25000")
        self.assertEqual(apply_free_shipping_base(Decimal("300000"), base), Decimal("0"))
        self.assertEqual(apply_free_shipping_base(Decimal("100000"), base), base)


class FreeShippingThresholdTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="free-shipping-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.shipping_method = ShippingMethod.objects.create(
            name="Standard",
            price=25000,
            estimated_days=2,
            active=True,
        )
        self.payment_method = PaymentMethod.objects.create(
            name="COD",
            code="COD",
            active=True,
        )
        self.category = Category.objects.create(name="TPCN", slug="tpcn-free-ship")
        self.product = Product.objects.create(
            name="Product Free Ship",
            mid="MID-FREE-SHIP-001",
            slug="product-free-ship",
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
            price_value=150000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-FREE-SHIP-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=5),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=100,
            remaining_quantity=100,
        )

    def _add_items_and_select_shipping(self, quantity):
        cart_data = self.client.get("/api/store/carts/current/").data
        v0 = cart_data["version"]
        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": quantity,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": add.data["version"],
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        return ship.data

    def test_cart_applies_free_shipping_when_subtotal_meets_threshold(self):
        cart = self._add_items_and_select_shipping(quantity=2)
        self.assertEqual(cart["subtotal"], "300000.00")
        self.assertEqual(cart["shipping_fee"], "0.00")
        self.assertTrue(cart["free_shipping_applied"])
        self.assertEqual(cart["total"], "300000.00")

    def test_cart_charges_shipping_below_threshold(self):
        cart = self._add_items_and_select_shipping(quantity=1)
        self.assertEqual(cart["subtotal"], "150000.00")
        self.assertEqual(cart["shipping_fee"], "25000.00")
        self.assertFalse(cart["free_shipping_applied"])
        self.assertEqual(cart["total"], "175000.00")

    def test_checkout_order_shipping_fee_zero_when_threshold_met(self):
        cart = self._add_items_and_select_shipping(quantity=2)
        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": cart["version"],
                "payment_method_id": self.payment_method.id,
                "shipping_address": "123 Free Ship Street",
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        self.assertEqual(checkout.data["shipping_fee"], "0.00")
        self.assertEqual(checkout.data["subtotal"], "300000.00")
        self.assertEqual(checkout.data["total"], "300000.00")

