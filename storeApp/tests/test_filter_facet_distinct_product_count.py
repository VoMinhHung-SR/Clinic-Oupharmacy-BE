"""Facet sidebar counts use distinct products, not variant rows."""
from django.test import TestCase
from rest_framework.test import APITestCase

from storeApp.models import Brand, Category, Product, ProductVariant, ProductVariantUnit
from storeApp.services.filter_builders import FilterBuilders
from storeApp.services.filter_extractors import FilterExtractors
from storeApp.services.filter_helpers import FilterHelpers
from storeApp.services.variant_listing import count_distinct_products


class FilterFacetDistinctProductCountTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.using("store").create(
            slug="facet-distinct-cat",
            name="Facet Distinct Cat",
        )
        self.brand = Brand.objects.using("store").create(
            name="Facet Brand",
            country="Việt Nam",
            active=True,
        )
        self.product = Product.objects.using("store").create(
            name="Multi Variant Product",
            mid="FACET-DISTINCT-001",
            slug="multi-variant-product",
            brand=self.brand,
        )
        self.product.assign_category(self.category, using="store", set_primary_if_none=True)

        self.variant_a = ProductVariant.objects.using("store").create(
            product=self.product,
            packing="Hộp",
            is_published=True,
            active=True,
            in_stock=5,
        )
        self.variant_b = ProductVariant.objects.using("store").create(
            product=self.product,
            packing="Vỉ",
            is_published=True,
            active=True,
            in_stock=3,
        )
        ProductVariantUnit.objects.using("store").create(
            variant=self.variant_a,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=80000,
            is_default=True,
            is_published=True,
        )
        ProductVariantUnit.objects.using("store").create(
            variant=self.variant_b,
            unit_name="Vỉ",
            quantity_in_base=1,
            price_value=50000,
            is_default=True,
            is_published=True,
        )

        self.queryset = FilterHelpers.get_category_queryset(self.category)

    def test_product_count_is_one_for_two_variants(self):
        self.assertEqual(self.queryset.count(), 2)
        self.assertEqual(count_distinct_products(self.queryset), 1)

    def test_brand_filter_counts_distinct_products(self):
        brand_ids_list, brands_dict = FilterHelpers.get_brand_data(self.queryset)
        variants = FilterExtractors.extract_variants(self.queryset, brand_ids_list, brands_dict)
        brand_filter = FilterBuilders.build_brand_filter(
            self.queryset, variants, brand_ids_list, brands_dict
        )
        self.assertIsNotNone(brand_filter)
        brand_option = next(o for o in brand_filter["options"] if o["value"] == "Facet Brand")
        self.assertEqual(brand_option["count"], 1)

    def test_price_range_counts_distinct_products(self):
        price_ranges = ["under_100k"]
        counts = FilterBuilders.compute_all_price_range_counts(self.queryset, price_ranges)
        self.assertEqual(counts["under_100k"], 1)

        legacy = FilterBuilders.count_by_price_range(self.queryset, "under_100k")
        self.assertEqual(legacy, 1)


class DynamicFiltersFkFallbackTests(APITestCase):
    """Dynamic filters must match category listing when products use primary FK only."""

    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.using("store").create(
            slug="fk-only-cat",
            name="FK Only Cat",
        )
        self.brand = Brand.objects.using("store").create(
            name="FK Brand",
            country="Pháp",
            active=True,
        )
        self.product = Product.objects.using("store").create(
            name="FK Only Product",
            mid="FK-FILTER-001",
            slug="fk-only-product",
            brand=self.brand,
            category=self.category,
        )
        self.variant = ProductVariant.objects.using("store").create(
            product=self.product,
            packing="Tuýp",
            is_published=True,
            active=True,
            in_stock=12,
        )
        ProductVariantUnit.objects.using("store").create(
            variant=self.variant,
            unit_name="Tuýp",
            quantity_in_base=1,
            price_value=250000,
            is_default=True,
            is_published=True,
        )

    def test_get_category_queryset_includes_fk_only_products(self):
        qs = FilterHelpers.get_category_queryset(self.category)
        self.assertEqual(qs.filter(product_id=self.product.id).count(), 1)

    def test_dynamic_filters_api_returns_brand_and_price(self):
        path = self.category.path_slug or self.category.slug
        res = self.client.get(f"/api/store/dynamic-filters/{path}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreater(body.get("productCount", 0), 0)
        filters = body.get("filters") or []
        filter_ids = {f["id"] for f in filters}
        self.assertIn("brand", filter_ids)
        self.assertIn("priceRange", filter_ids)


class FkOnlyProductDetailResolveTests(APITestCase):
    """Product detail resolve/listing when ProductCategory M2M rows are missing."""

    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.using("store").create(
            slug="fk-detail-cat",
            name="FK Detail Cat",
        )
        self.product = Product.objects.using("store").create(
            name="FK Detail Product",
            mid="FK-DETAIL-001",
            slug="fk-detail-product",
            category=self.category,
        )
        self.variant = ProductVariant.objects.using("store").create(
            product=self.product,
            packing="Hộp",
            is_published=True,
            active=True,
            in_stock=5,
        )

    def test_resolve_path_product_with_fk_only_category(self):
        path = f"{self.category.path_slug or self.category.slug}/{self.product.slug}"
        from storeApp.services.store_path_resolver import resolve_store_path

        resolved = resolve_store_path(path, using="store")
        self.assertEqual(resolved["page"], "product")
        self.assertEqual(resolved["product_slug"], self.product.slug)

    def test_detail_api_with_fk_only_category(self):
        path = f"{self.category.path_slug or self.category.slug}/{self.product.slug}"
        res = self.client.get(f"/api/store/{path}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("product", {}).get("slug"), self.product.slug)
