"""Cart catalog direct savings (P2 / D-PRC-05)."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import (
    CartItem,
    Category,
    MedicineBatch,
    Product,
    ProductVariant,
    ProductVariantUnit,
)
from storeApp.services.cart_service import (
    _build_context,
    add_or_update_item,
    get_or_create_active_cart,
    recalculate_cart,
)
from storeApp.services.product_pricing import catalog_direct_savings_line, list_price_snapshot_from_unit


class CatalogDirectSavingsHelpersTests(TestCase):
    databases = {"default", "store"}

    def test_list_snapshot_only_when_compare_above_sale(self):
        unit = ProductVariantUnit(compare_at_price=Decimal("606000"), price_value=Decimal("424200"))
        self.assertEqual(list_price_snapshot_from_unit(unit, Decimal("424200")), Decimal("606000"))
        self.assertIsNone(list_price_snapshot_from_unit(unit, Decimal("606000")))

    def test_catalog_savings_line(self):
        self.assertEqual(
            catalog_direct_savings_line(
                list_price_snapshot=Decimal("606000"),
                sale_price_snapshot=Decimal("424200"),
                quantity=2,
            ),
            Decimal("363600"),
        )
        self.assertEqual(
            catalog_direct_savings_line(
                list_price_snapshot=None,
                sale_price_snapshot=Decimal("100000"),
                quantity=1,
            ),
            Decimal("0"),
        )


class CatalogDirectSavingsServiceTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.create(name="Sale", slug="sale-cat")
        product = Product.objects.create(
            name="Promo Product",
            slug="promo-product",
            mid="MID-SAV-1",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp",
            is_published=True,
            in_stock=20,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=Decimal("424200"),
            compare_at_price=Decimal("606000"),
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-SAV-1",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=1),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=20,
            remaining_quantity=20,
        )
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="savings-user@example.com",
            password="test-pass-123",
        )
        self.cart = get_or_create_active_cart(user_id=self.user.id, using="store")

    def test_add_item_snapshots_list_and_recalc_savings(self):
        add_or_update_item(
            cart=self.cart,
            product_variant_id=self.variant.id,
            product_variant_unit_id=self.unit.id,
            quantity=2,
            using="store",
        )
        cart = recalculate_cart(cart=self.cart, using="store", expected_version=self.cart.version)
        item = CartItem.objects.get(cart=cart, product_variant=self.variant)
        self.assertEqual(item.unit_price_snapshot, Decimal("424200"))
        self.assertEqual(item.list_price_snapshot, Decimal("606000"))
        self.assertEqual(cart.subtotal, Decimal("848400"))
        self.assertEqual(cart.catalog_direct_savings_total, Decimal("363600"))

    def test_partial_checkout_context_savings_scoped_to_lines(self):
        product_b = Product.objects.create(
            name="Regular Product",
            slug="regular-product",
            mid="MID-SAV-2",
            category=self.category,
        )
        variant_b = ProductVariant.objects.create(
            product=product_b,
            packing="Hộp",
            is_published=True,
            in_stock=20,
        )
        unit_b = ProductVariantUnit.objects.create(
            variant=variant_b,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=Decimal("100000"),
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-SAV-2",
            product_variant=variant_b,
            import_date=timezone.now().date() - timedelta(days=1),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=20,
            remaining_quantity=20,
        )

        add_or_update_item(
            cart=self.cart,
            product_variant_id=self.variant.id,
            product_variant_unit_id=self.unit.id,
            quantity=1,
            using="store",
        )
        add_or_update_item(
            cart=self.cart,
            product_variant_id=variant_b.id,
            product_variant_unit_id=unit_b.id,
            quantity=1,
            using="store",
        )
        cart = recalculate_cart(cart=self.cart, using="store", expected_version=self.cart.version)
        promo_item = CartItem.objects.get(cart=cart, product_variant=self.variant)

        _, _, _, _, _, scoped_savings = _build_context(
            cart=cart,
            using="store",
            item_ids=[promo_item.id],
        )
        self.assertEqual(scoped_savings, Decimal("181800"))


class CatalogDirectSavingsApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="savings-api@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(name="API Sale", slug="api-sale")
        product = Product.objects.create(
            name="API Promo",
            slug="api-promo",
            mid="MID-API-SAV",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp",
            is_published=True,
            in_stock=10,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=Decimal("70000"),
            compare_at_price=Decimal("100000"),
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-API-SAV",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=1),
            expiry_date=timezone.now().date() + timedelta(days=200),
            quantity=10,
            remaining_quantity=10,
        )

    def test_cart_current_exposes_catalog_direct_savings_total(self):
        current = self.client.get("/api/store/carts/current/")
        self.assertEqual(current.status_code, 200)
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
        self.assertEqual(add.data["catalog_direct_savings_total"], "60000.00")
        self.assertEqual(add.data["subtotal"], "140000.00")
        line = add.data["items"][0]
        self.assertEqual(line["list_price_snapshot"], "100000.00")
        self.assertEqual(line["catalog_savings"], "60000.00")
