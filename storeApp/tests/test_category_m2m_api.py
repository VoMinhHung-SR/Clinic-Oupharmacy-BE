"""Category list/detail/search API with ProductCategory M2M."""
from rest_framework.test import APITestCase

from storeApp.models import (
    Category,
    Product,
    ProductVariant,
    ProductVariantUnit,
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

    def test_search_filters_by_secondary_category_m2m(self):
        r = self.client.get(
            "/api/store/search/",
            {"q": "Api M2M", "category": str(self.leaf_b.id)},
        )
        self.assertEqual(r.status_code, 200)
        ids = [row["id"] for row in r.json().get("items", [])]
        self.assertIn(self.variant.id, ids)
