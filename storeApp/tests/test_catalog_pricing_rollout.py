"""P4 catalog pricing rollout — audit, cleanup, E2E."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import (
    Campaign,
    CartItem,
    Category,
    MedicineBatch,
    OrderItem,
    PaymentMethod,
    Product,
    ProductVariant,
    ProductVariantUnit,
    ShippingMethod,
)
from storeApp.services.catalog_pricing_audit import (
    audit_catalog_pricing,
    backfill_cart_list_price_snapshots,
    clear_legacy_reverse_compare_at,
    is_legacy_reverse_compare_at,
)
from storeApp.services.cart_service import add_or_update_item, get_or_create_active_cart, recalculate_cart
from storeApp.services.product_pricing import tier_promo_prices
from storeApp.services.product_promotion import apply_unit_promotion


class LegacyCompareAtDetectionTests(TestCase):
    databases = {"default", "store"}

    def test_detects_p0_reverse_pattern(self):
        # price 606k unchanged; compare ≈ 606 / 0.7
        self.assertTrue(
            is_legacy_reverse_compare_at(
                price_value=Decimal("606000"),
                compare_at_price=Decimal("865714"),
            )
        )

    def test_rejects_p1_real_promo_shape(self):
        # P1 list/sale — not hot-sale reverse-from-price pattern when scoped by mid
        self.assertFalse(
            is_legacy_reverse_compare_at(
                price_value=Decimal("424200"),
                compare_at_price=Decimal("606000"),
                product_mid="MID-ROLLOUT-1",
                hot_sale_mids={"MID-OTHER"},
            )
        )

    def test_legacy_requires_hot_sale_mid_when_scoped(self):
        self.assertFalse(
            is_legacy_reverse_compare_at(
                price_value=Decimal("606000"),
                compare_at_price=Decimal("865714"),
                product_mid="MID-NOT-HOT",
                hot_sale_mids={"MID-HOT-ONLY"},
            )
        )


class CatalogPricingCleanupTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.create(name="Legacy", slug="legacy-cleanup")
        product = Product.objects.create(
            name="Legacy Unit",
            slug="legacy-unit",
            mid="MID-LEG-1",
            category=self.category,
        )
        variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp",
            is_published=True,
            in_stock=10,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=Decimal("606000"),
            compare_at_price=Decimal("865714"),
            is_default=True,
            is_published=True,
        )

    def test_clear_legacy_nulls_compare_at(self):
        from storeApp.models import Campaign, CampaignProduct
        from storeApp.services.hot_sale_campaign import HOT_SALE_CAMPAIGN_SLUG

        campaign = Campaign.objects.create(
            slug=HOT_SALE_CAMPAIGN_SLUG,
            name="Hot",
            title="Hot",
            status=Campaign.STATUS_ACTIVE,
        )
        CampaignProduct.objects.create(campaign=campaign, product_mid="MID-LEG-1", sort_order=0)

        cleared = clear_legacy_reverse_compare_at(using="store")
        self.assertEqual(cleared, 1)
        self.unit.refresh_from_db()
        self.assertIsNone(self.unit.compare_at_price)

    def test_audit_reports_legacy_count(self):
        from storeApp.models import Campaign, CampaignProduct
        from storeApp.services.hot_sale_campaign import HOT_SALE_CAMPAIGN_SLUG

        campaign = Campaign.objects.create(
            slug=HOT_SALE_CAMPAIGN_SLUG,
            name="Hot",
            title="Hot",
            status=Campaign.STATUS_ACTIVE,
        )
        CampaignProduct.objects.create(campaign=campaign, product_mid="MID-LEG-1", sort_order=0)

        report = audit_catalog_pricing(using="store")
        self.assertGreaterEqual(report.legacy_compare_only_count, 1)


class CatalogPricingRolloutE2ETests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="rollout-e2e@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.shipping_method = ShippingMethod.objects.create(
            name="Rollout Ship",
            price=20000,
            estimated_days=2,
            active=True,
        )
        self.payment_method = PaymentMethod.objects.create(
            name="Rollout COD",
            code="ROLLOUT_COD",
            active=True,
        )
        self.category = Category.objects.create(name="Rollout", slug="rollout-e2e")
        self.product = Product.objects.create(
            name="Rollout Promo",
            slug="rollout-promo",
            mid="MID-ROLLOUT-1",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp",
            is_published=True,
            in_stock=50,
            product_ranking=100,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=Decimal("100000"),
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-ROLLOUT-1",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=1),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=50,
            remaining_quantity=50,
        )

    def test_hot_sale_to_cart_savings_to_checkout(self):
        campaign = Campaign.objects.create(
            slug="rollout-e2e-promo",
            name="Rollout E2E",
            title="Rollout E2E",
            status=Campaign.STATUS_ACTIVE,
        )
        promo = tier_promo_prices(self.unit, 30)
        assert promo is not None
        apply_unit_promotion(
            campaign=campaign,
            unit=self.unit,
            promo=promo,
            tier_percent=30,
            using="store",
        )

        self.unit.refresh_from_db()
        self.assertLess(self.unit.price_value, Decimal("100000"))
        self.assertGreater(self.unit.compare_at_price or 0, self.unit.price_value)

        current = self.client.get("/api/store/carts/current/")
        v0 = current.data["version"]
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
        self.assertGreater(float(add.data.get("catalog_direct_savings_total") or 0), 0)
        line = add.data["items"][0]
        self.assertIsNotNone(line.get("list_price_snapshot"))

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
                "shipping_address": "Rollout E2E address",
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)

        order_item = OrderItem.objects.filter(order__user_id=self.user.id).first()
        self.assertIsNotNone(order_item)
        assert order_item is not None
        self.assertIsNotNone(order_item.list_price_snapshot)
        self.assertEqual(order_item.price, self.unit.price_value)


class CartListSnapshotBackfillTests(TestCase):
    databases = {"default", "store"}

    def test_backfill_sets_list_from_compare_at(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(email="backfill@example.com", password="x")
        category = Category.objects.create(name="BF", slug="bf")
        product = Product.objects.create(
            name="BF",
            slug="bf-prod",
            mid="MID-BF",
            category=category,
        )
        variant = ProductVariant.objects.create(product=product, packing="H", is_published=True, in_stock=5)
        unit = ProductVariantUnit.objects.create(
            variant=variant,
            unit_name="H",
            quantity_in_base=1,
            price_value=Decimal("80000"),
            compare_at_price=Decimal("100000"),
            is_default=True,
            is_published=True,
        )
        cart = get_or_create_active_cart(user_id=user.id, using="store")
        add_or_update_item(
            cart=cart,
            product_variant_id=variant.id,
            product_variant_unit_id=unit.id,
            quantity=1,
            using="store",
        )
        item = CartItem.objects.get(cart=cart)
        item.list_price_snapshot = None
        item.save(update_fields=["list_price_snapshot"])

        updated = backfill_cart_list_price_snapshots(using="store")
        self.assertEqual(updated, 1)
        item.refresh_from_db()
        self.assertEqual(item.list_price_snapshot, Decimal("100000"))

        cart = recalculate_cart(cart=cart, using="store", expected_version=cart.version)
        self.assertEqual(cart.catalog_direct_savings_total, Decimal("20000"))
