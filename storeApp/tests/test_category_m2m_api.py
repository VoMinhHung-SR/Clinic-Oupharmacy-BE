"""Category list/detail/search API with ProductCategory M2M."""
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

class ProductsByCategoryM2MAPITests(APITestCase):
    """List/detail/search respect ProductCategory M2M (Phase 2)."""

    databases = {"default", "store"}

    def setUp(self):
        root_a, _ = Category.objects.using("store").get_or_create(
            slug="api-m2m-cat-a", parent=None, defaults={"name": "Api M2M Cat A"}
        )
        root_a = Category.objects.using("store").get(pk=root_a.pk)
        leaf_a, _ = Category.objects.using("store").get_or_create(
            slug="api-m2m-leaf-a", parent=root_a, defaults={"name": "Api Leaf A"}
        )
        leaf_a = Category.objects.using("store").get(pk=leaf_a.pk)

        root_b, _ = Category.objects.using("store").get_or_create(
            slug="api-m2m-cat-b", parent=None, defaults={"name": "Api M2M Cat B"}
        )
        root_b = Category.objects.using("store").get(pk=root_b.pk)
        leaf_b, _ = Category.objects.using("store").get_or_create(
            slug="api-m2m-leaf-b", parent=root_b, defaults={"name": "Api Leaf B"}
        )
        leaf_b = Category.objects.using("store").get(pk=leaf_b.pk)

        orphan, _ = Category.objects.using("store").get_or_create(
            slug="api-m2m-orphan", parent=None, defaults={"name": "Orphan cat"}
        )
        orphan = Category.objects.using("store").get(pk=orphan.pk)

        self.leaf_a = leaf_a
        self.leaf_b = leaf_b
        self.orphan = orphan

        product = Product.objects.using("store").create(
            name="Api M2M Product X",
            mid="TEST-M2M-API-001",
            slug="api-m2m-product-x",
        )
        product.assign_category(leaf_a, using="store", set_primary_if_none=True)
        product.assign_category(leaf_b, using="store", set_primary_if_none=True)

        self.product = Product.objects.using("store").get(pk=product.pk)
        self.variant = ProductVariant.objects.using("store").create(
            product=self.product,
            packing="Hộp",
            is_published=True,
            in_stock=10,
            product_ranking=1,
        )
        ProductVariantUnit.objects.using("store").create(
            variant=self.variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=50000,
            is_default=True,
            is_published=True,
        )

    def _variant_ids_from_category_list_response(self, data):
        if "results" in data:
            return [row.get("id") for row in data["results"]]
        return [row.get("id") for row in data.get("products", [])]

    def test_list_contains_variant_under_leaf_a_and_leaf_b(self):
        pa = self.leaf_a.path_slug or self.leaf_a.slug
        pb = self.leaf_b.path_slug or self.leaf_b.slug
        ra = self.client.get(f"/api/store/{pa}/")
        rb = self.client.get(f"/api/store/{pb}/")
        self.assertEqual(ra.status_code, 200)
        self.assertEqual(rb.status_code, 200)
        self.assertIn(self.variant.id, self._variant_ids_from_category_list_response(ra.json()))
        self.assertIn(self.variant.id, self._variant_ids_from_category_list_response(rb.json()))

    def test_detail_200_when_category_path_in_m2m(self):
        path = self.leaf_b.path_slug or self.leaf_b.slug
        r = self.client.get(f"/api/store/{path}/api-m2m-product-x/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("category_info", body)
        ci = body["category_info"]
        self.assertGreaterEqual(len(ci.get("category_slugs", [])), 2)
        self.assertEqual(ci.get("listed_under_slug"), path)

    def test_detail_404_when_category_not_in_m2m(self):
        path = self.orphan.path_slug or self.orphan.slug
        r = self.client.get(f"/api/store/{path}/api-m2m-product-x/")
        self.assertEqual(r.status_code, 404)

    def test_detail_200_when_url_is_ancestor_of_assigned_leaf(self):
        """List can show product under parent tree; detail URL may use parent path."""
        root, _ = Category.objects.using("store").get_or_create(
            slug="api-m2m-tree-root", parent=None, defaults={"name": "Tree Root"}
        )
        root = Category.objects.using("store").get(pk=root.pk)
        child, _ = Category.objects.using("store").get_or_create(
            slug="api-m2m-tree-child", parent=root, defaults={"name": "Tree Child"}
        )
        child = Category.objects.using("store").get(pk=child.pk)
        leaf_only, _ = Category.objects.using("store").get_or_create(
            slug="api-m2m-tree-leaf-only", parent=child, defaults={"name": "Tree Leaf Only"}
        )
        leaf_only = Category.objects.using("store").get(pk=leaf_only.pk)

        p = Product.objects.using("store").create(
            name="Ancestor Detail Product",
            mid="TEST-ANC-DETAIL-001",
            slug="ancestor-detail-product",
        )
        p.assign_category(leaf_only, using="store", set_primary_if_none=True)
        ProductVariant.objects.using("store").create(
            product=p,
            packing="Lọ",
            is_published=True,
            in_stock=5,
            product_ranking=1,
        )

        parent_path = child.path_slug or child.slug
        r = self.client.get(f"/api/store/{parent_path}/ancestor-detail-product/")
        self.assertEqual(r.status_code, 200, r.content)
        listed = (r.json().get("category_info") or {}).get("listed_under_slug")
        self.assertEqual(listed, parent_path)

    def test_search_filters_by_secondary_category_m2m(self):
        r = self.client.get(
            "/api/store/search/",
            {"q": "Api M2M", "category": str(self.leaf_b.id)},
        )
        self.assertEqual(r.status_code, 200)
        ids = [row["id"] for row in r.json().get("items", [])]
        self.assertIn(self.variant.id, ids)


class OrderVoucherMultiCategoryTests(APITestCase):
    """Voucher applicable_categories matches any M2M slug, not only primary."""

    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="m2m-voucher-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.shipping_method = ShippingMethod.objects.create(
            name="Standard", price=30000, estimated_days=2, active=True
        )
        self.payment_method = PaymentMethod.objects.create(
            name="COD", code="COD", active=True
        )

        root_a, _ = Category.objects.using("store").get_or_create(
            slug="voucher-m2m-a", parent=None, defaults={"name": "Voucher M2M A"}
        )
        root_a = Category.objects.using("store").get(pk=root_a.pk)
        self.leaf_a, _ = Category.objects.using("store").get_or_create(
            slug="voucher-m2m-leaf-a", parent=root_a, defaults={"name": "Voucher Leaf A"}
        )
        self.leaf_a = Category.objects.using("store").get(pk=self.leaf_a.pk)

        root_b, _ = Category.objects.using("store").get_or_create(
            slug="voucher-m2m-b", parent=None, defaults={"name": "Voucher M2M B"}
        )
        root_b = Category.objects.using("store").get(pk=root_b.pk)
        self.leaf_b, _ = Category.objects.using("store").get_or_create(
            slug="voucher-m2m-leaf-b", parent=root_b, defaults={"name": "Voucher Leaf B"}
        )
        self.leaf_b = Category.objects.using("store").get(pk=self.leaf_b.pk)

        product = Product.objects.using("store").create(
            name="Voucher M2M Product",
            mid="TEST-M2M-VOUCHER-001",
            slug="voucher-m2m-product",
        )
        product.assign_category(self.leaf_a, using="store", set_primary_if_none=True)
        product.assign_category(self.leaf_b, using="store", set_primary_if_none=True)
        self.product = Product.objects.using("store").get(pk=product.pk)

        self.variant = ProductVariant.objects.using("store").create(
            product=self.product,
            packing="Hộp",
            in_stock=50,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.using("store").create(
            variant=self.variant,
            quantity_in_base=1,
            unit_name="Hộp",
            price_value=100000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.using("store").create(
            batch_number="BATCH-M2M-VOUCHER-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=3),
            expiry_date=timezone.now().date() + timedelta(days=200),
            quantity=50,
            remaining_quantity=50,
        )

        secondary_slug = self.leaf_b.path_slug or self.leaf_b.slug
        self.voucher = Voucher.objects.create(
            code="M2MSECCAT10",
            scope=Voucher.ORDER_DISCOUNT,
            type="FIXED",
            value=Decimal("10000"),
            is_active=True,
            start_at=timezone.now() - timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1),
            usage_limit=10,
            applicable_categories=[secondary_slug],
        )

    def test_order_voucher_applies_when_secondary_category_in_m2m(self):
        response = self.client.post(
            "/api/store/orders/",
            {
                "shipping_address": "123 Test",
                "shipping_method_id": self.shipping_method.id,
                "payment_method_id": self.payment_method.id,
                "order_voucher_code": self.voucher.code,
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
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["discount_amount"], "10000.00")
