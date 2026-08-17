"""Checkout campaign_id attribution (P5-T2 / D-10)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import (
    Campaign,
    Category,
    MedicineBatch,
    Order,
    PaymentMethod,
    Product,
    ProductVariant,
    ProductVariantUnit,
    ShippingMethod,
)


class CartCheckoutCampaignAttributionTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="checkout-campaign@example.com",
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
            code="COD-CAMP",
            active=True,
        )
        category = Category.objects.create(name="Camp Cat", slug="camp-cat")
        product = Product.objects.create(
            name="Camp Product",
            mid="MID-CAMP-ATTR",
            slug="camp-product",
            category=category,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp",
            in_stock=50,
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
            batch_number="BATCH-CAMP-ATTR",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=3),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=50,
            remaining_quantity=50,
        )
        now = timezone.now()
        self.campaign = Campaign.objects.create(
            name="Attr",
            slug="attr-camp",
            title="Attr",
            status=Campaign.STATUS_ACTIVE,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=2),
        )

    def _prepare_cart_version(self):
        cart = self.client.get("/api/store/carts/current/").data
        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": cart["version"],
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200, add.data)
        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": add.data["version"],
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200, ship.data)
        return ship.data["version"]

    def _delivery(self):
        return {
            "orderer": {"name": "Đặt Hàng", "phone": "0382590839", "email": "a@example.com"},
            "recipient": {"name": "Nhận Hàng", "phone": "0382590839"},
            "address": {"province": "HN", "district": "Ba Đình", "ward": "P1", "detail": "12 Phố Huế"},
        }

    def test_valid_campaign_id_stored(self):
        version = self._prepare_cart_version()
        res = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": version,
                "payment_method_id": self.payment_method.id,
                "delivery": self._delivery(),
                "campaign_id": self.campaign.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data.get("campaign_id"), self.campaign.id)
        order = Order.objects.get(id=res.data["id"])
        self.assertEqual(order.campaign_id, self.campaign.id)

    def test_invalid_campaign_id_ignored(self):
        version = self._prepare_cart_version()
        res = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": version,
                "payment_method_id": self.payment_method.id,
                "delivery": self._delivery(),
                "campaign_id": 999999,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIsNone(res.data.get("campaign_id"))
        order = Order.objects.get(id=res.data["id"])
        self.assertIsNone(order.campaign_id)
