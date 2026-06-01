"""Facet sidebar counts use distinct products, not variant rows."""
from django.test import TestCase

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
