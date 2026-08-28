"""Cart eligible voucher offers API."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APITestCase

from storeApp.models import (
    Category,
    MedicineBatch,
    PaymentMethod,
    Product,
    ProductVariant,
    ProductVariantUnit,
    ShippingMethod,
    Voucher,
)


class CartEligibleVouchersApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="cart-voucher-offers@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        ShippingMethod.objects.create(name="Standard", price=30000, estimated_days=2, active=True)
        PaymentMethod.objects.create(name="COD", code="COD", active=True)

        category = Category.objects.create(name="Thuốc ho", slug="thuoc-ho")
        product = Product.objects.create(
            name="Thuốc ho A",
            mid="MID-CVO-001",
            slug="thuoc-ho-a-cvo",
            category=category,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp",
            in_stock=100,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=1,
            unit_name="Hộp",
            unit_order=0,
            price_value=600000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-CVO-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=5),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=100,
            remaining_quantity=100,
        )

        now = timezone.now()
        self.sale20 = Voucher.objects.create(
            code="SALE20",
            scope=Voucher.ORDER_DISCOUNT,
            type="PERCENT",
            value=Decimal("20"),
            max_discount=Decimal("100000"),
            min_order_value=Decimal("200000"),
            is_active=True,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=30),
            description="Giảm 20%",
        )
        self.sale30 = Voucher.objects.create(
            code="SALE30",
            scope=Voucher.ORDER_DISCOUNT,
            type="PERCENT",
            value=Decimal("30"),
            max_discount=Decimal("150000"),
            min_order_value=Decimal("500000"),
            is_active=True,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=30),
            description="Giảm 30%",
        )
        self.sale10_low_min = Voucher.objects.create(
            code="SALE10",
            scope=Voucher.ORDER_DISCOUNT,
            type="PERCENT",
            value=Decimal("10"),
            max_discount=Decimal("50000"),
            min_order_value=Decimal("100000"),
            is_active=True,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=30),
            description="Giảm 10%",
        )

        cart_data = self.client.get("/api/store/carts/current/").data
        add_resp = self.client.post(
            "/api/store/carts/items/",
            {
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
                "expected_version": cart_data["version"],
            },
            format="json",
        )
        self.assertEqual(add_resp.status_code, 200, add_resp.data)

    def test_eligible_vouchers_returns_best_order_voucher_by_discount(self):
        response = self.client.get("/api/store/carts/eligible-vouchers/")
        self.assertEqual(response.status_code, 200, response.data)
        codes = [row["code"] for row in response.data["order_vouchers"]]
        self.assertIn("SALE20", codes)
        self.assertIn("SALE30", codes)
        self.assertEqual(response.data["best_order_voucher_code"], "SALE30")
        best = response.data["order_vouchers"][0]
        self.assertEqual(best["code"], "SALE30")
        self.assertGreater(Decimal(best["estimated_discount"]), Decimal("100000"))

    def test_eligible_vouchers_respects_min_order(self):
        Voucher.objects.filter(code="SALE30").update(min_order_value=Decimal("700000"))
        response = self.client.get("/api/store/carts/eligible-vouchers/")
        self.assertEqual(response.status_code, 200, response.data)
        codes = [row["code"] for row in response.data["order_vouchers"]]
        self.assertNotIn("SALE30", codes)
        self.assertEqual(response.data["best_order_voucher_code"], "SALE20")
