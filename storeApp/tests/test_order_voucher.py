"""Order creation with order/shipping voucher validation."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APITestCase

from storeApp.models import (
    Category,
    MedicineBatch,
    Order,
    PaymentMethod,
    Product,
    ProductVariant,
    ProductVariantUnit,
    ShippingMethod,
    Voucher,
    VoucherRedemption,
)

class OrderVoucherCreateTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="voucher-user@example.com",
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
            mid="MID-HOA",
            slug="thuoc-ho-a",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp",
            in_stock=200,
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
            batch_number="BATCH-VOUCHER-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=7),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=200,
            remaining_quantity=200,
        )

    def _create_voucher(self, code, scope, voucher_type="PERCENT", value="10", **kwargs):
        defaults = {
            "code": code,
            "scope": scope,
            "type": voucher_type,
            "value": Decimal(str(value)),
            "is_active": True,
            "start_at": timezone.now() - timedelta(days=1),
            "end_at": timezone.now() + timedelta(days=1),
            "usage_limit": 10,
        }
        defaults.update(kwargs)
        return Voucher.objects.create(**defaults)

    def _payload(self, **extra):
        payload = {
            "shipping_address": "123 Test Street",
            "notes": "ghi chu",
            "shipping_method_id": self.shipping_method.id,
            "payment_method_id": self.payment_method.id,
            "items": [
                {
                    "product_variant_id": self.variant.id,
                    "product_variant_unit_id": self.unit.id,
                    "quantity": 1,
                    "price": "100000",
                }
            ],
            "subtotal": "1",
            "shipping_fee": "1",
            "total": "1",
        }
        payload.update(extra)
        return payload

    def test_create_order_applies_one_order_voucher_and_one_shipping_voucher(self):
        order_voucher = self._create_voucher(
            code="ORDER10",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="PERCENT",
            value="10",
            per_user_limit=2,
        )
        shipping_voucher = self._create_voucher(
            code="SHIP5",
            scope=Voucher.SHIPPING_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
        )

        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code, shipping_voucher_code=shipping_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["discount_amount"], "10000.00")
        self.assertEqual(response.data["shipping_discount_amount"], "5000.00")
        self.assertEqual(response.data["shipping_fee"], "25000.00")
        self.assertEqual(response.data["total"], "115000.00")
        self.assertEqual(response.data["order_voucher_code"], "ORDER10")
        self.assertEqual(response.data["shipping_voucher_code"], "SHIP5")

        order = Order.objects.get(id=response.data["id"])
        self.assertEqual(order.order_voucher_id, order_voucher.id)
        self.assertEqual(order.shipping_voucher_id, shipping_voucher.id)
        self.assertEqual(VoucherRedemption.objects.filter(order=order).count(), 2)

    def test_create_order_rejects_wrong_scope_codes(self):
        shipping_voucher = self._create_voucher(
            code="SHIPONLY",
            scope=Voucher.SHIPPING_DISCOUNT,
            voucher_type="FIXED",
            value="10000",
        )

        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=shipping_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("order_voucher_code must be ORDER_DISCOUNT voucher", response.data["error"])

    def test_create_order_enforces_per_user_limit(self):
        order_voucher = self._create_voucher(
            code="ONEPERUSER",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="10000",
            per_user_limit=1,
        )

        first = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(
            second.data["details"]["order_voucher_code"][0],
            "Per-user limit exceeded",
        )

    def test_create_order_total_is_calculated_server_side(self):
        response = self.client.post("/api/store/orders/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["subtotal"], "100000.00")
        self.assertEqual(response.data["shipping_fee"], "30000.00")
        self.assertEqual(response.data["total"], "130000.00")

    def test_create_order_rejects_voucher_not_started(self):
        order_voucher = self._create_voucher(
            code="NOTSTART",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=2),
        )
        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["details"]["order_voucher_code"][0], "Voucher is not started")

    def test_create_order_rejects_voucher_expired(self):
        order_voucher = self._create_voucher(
            code="EXPIRED",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
            start_at=timezone.now() - timedelta(days=4),
            end_at=timezone.now() - timedelta(days=1),
        )
        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["details"]["order_voucher_code"][0], "Voucher is expired")

    def test_create_order_rejects_usage_limit_reached(self):
        order_voucher = self._create_voucher(
            code="LIMITREACHED",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
            usage_limit=1,
            used_count=1,
        )
        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["details"]["order_voucher_code"][0],
            "Voucher usage limit exceeded",
        )

    def test_create_order_rejects_min_order_not_met(self):
        order_voucher = self._create_voucher(
            code="MIN200K",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
            min_order_value=Decimal("200000"),
        )
        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["details"]["order_voucher_code"][0],
            "Minimum order value not met",
        )

