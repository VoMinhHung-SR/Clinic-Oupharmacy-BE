"""P2 facet SQL path and cache invalidation tests."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from storeApp.models import Brand, Category, Product, ProductVariant, ProductVariantUnit
from storeApp.services.dynamic_filters_service import DynamicFiltersService
from storeApp.services.facet_sql_aggregator import FacetSqlAggregator
from storeApp.services.filter_extractors import FilterExtractors
from storeApp.services.filter_helpers import FilterHelpers


class FacetSqlAggregatorTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.using("store").create(
            slug="sql-facet-cat",
            name="SQL Facet Cat",
        )
        self.brand = Brand.objects.using("store").create(
            name="SQL Brand",
            country="Đức",
            active=True,
        )
        self.product = Product.objects.using("store").create(
            name="SQL Facet Product",
            mid="SQL-FACET-001",
            slug="sql-facet-product",
            brand=self.brand,
        )
        self.product.assign_category(self.category, using="store", set_primary_if_none=True)
        self.variant = ProductVariant.objects.using("store").create(
            product=self.product,
            packing="Hộp",
            is_published=True,
            active=True,
            in_stock=4,
        )
        ProductVariantUnit.objects.using("store").create(
            variant=self.variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=150000,
            is_default=True,
            is_published=True,
        )
        self.queryset = FilterHelpers.get_category_queryset(self.category)
        self.brand_ids, self.brands_dict = FilterHelpers.get_brand_data(self.queryset)

    def test_sql_variants_include_brand_country_price_without_iterator(self):
        variants = FacetSqlAggregator.build_sql_variants(self.queryset, self.brands_dict)
        self.assertIn("SQL Brand", variants["brands"])
        self.assertIn("Đức", variants["countries"])
        self.assertGreater(variants["priceStats"].get("min", 0), 0)
        self.assertTrue(variants["priceRanges"])

    def test_extract_variants_skips_iterator_when_no_text_filters_enabled(self):
        with patch.object(
            FilterExtractors,
            "_extract_text_facets",
            wraps=FilterExtractors._extract_text_facets,
        ) as extract_text:
            variants = FilterExtractors.extract_variants(
                self.queryset,
                self.brand_ids,
                self.brands_dict,
                enabled_filters=["brand", "country", "priceRange"],
            )
            extract_text.assert_not_called()
        self.assertIn("SQL Brand", variants["brands"])
        self.assertEqual(variants["targetAudiences"], [])


class DynamicFiltersCacheTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        cache.clear()
        self.category = Category.objects.using("store").create(
            slug="cache-facet-cat",
            name="Cache Facet Cat",
        )

    def test_invalidate_all_cache_bumps_version(self):
        before = DynamicFiltersService._cache_version()
        DynamicFiltersService.invalidate_all_cache()
        after = DynamicFiltersService._cache_version()
        self.assertEqual(after, before + 1)

    def test_versioned_cache_key_changes_after_invalidate_all(self):
        slug = self.category.path_slug or self.category.slug
        key_before = DynamicFiltersService._cache_key(slug)
        DynamicFiltersService.invalidate_all_cache()
        key_after = DynamicFiltersService._cache_key(slug)
        self.assertNotEqual(key_before, key_after)
