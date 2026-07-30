"""Search facet distinct-product counts and cache tests."""
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APITestCase

from storeApp.models import Brand, Category, Product, ProductVariant, ProductVariantUnit
from storeApp.services.search_facets_service import SearchFacetsService
from storeApp.viewsets.product import annotate_variant_unit_price


class SearchFacetDistinctProductCountTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.using("store").create(
            slug="search-facet-cat",
            name="Search Facet Cat",
        )
        self.brand = Brand.objects.using("store").create(
            name="Search Facet Brand",
            country="Việt Nam",
            active=True,
        )
        self.product = Product.objects.using("store").create(
            name="Multi Variant Product",
            mid="SEARCH-FACET-001",
            slug="search-facet-product",
            brand=self.brand,
        )
        self.product.assign_category(self.category, using="store", set_primary_if_none=True)

        for packing, price in [("Hộp", 80000), ("Vỉ", 50000)]:
            variant = ProductVariant.objects.using("store").create(
                product=self.product,
                packing=packing,
                is_published=True,
                active=True,
                in_stock=5,
            )
            ProductVariantUnit.objects.using("store").create(
                variant=variant,
                unit_name=packing,
                quantity_in_base=1,
                price_value=price,
                is_default=True,
                is_published=True,
            )

        from storeApp.services.product_category_helpers import (
            category_tree_ids,
            product_in_categories_q,
        )

        category_ids = category_tree_ids(self.category, using="store")
        self.queryset = annotate_variant_unit_price(
            ProductVariant.objects.using("store")
            .filter(
                active=True,
                is_published=True,
                product__active=True,
            )
            .filter(product_in_categories_q(category_ids, using="store"))
            .select_related("product", "product__brand"),
            db_alias="store",
        )

    def test_brand_facet_counts_distinct_products(self):
        facets = SearchFacetsService.build_facets(self.queryset, include_category=False)
        brand = next(b for b in facets["brand"] if b["name"] == "Search Facet Brand")
        self.assertEqual(brand["count"], 1)

    def test_origin_country_facet_from_brand_country(self):
        facets = SearchFacetsService.build_facets(self.queryset, include_category=False)
        origins = facets["origin_country"]
        self.assertEqual(origins[0]["key"], "Việt Nam")
        self.assertEqual(origins[0]["count"], 1)

    def test_origin_country_facet_drops_junk_labels(self):
        junk_brand = Brand.objects.using("store").create(
            name="Junk Origin Brand",
            country="Hộp x 15ml",
            active=True,
        )
        product = Product.objects.using("store").create(
            name="Junk Origin Product",
            mid="SEARCH-FACET-JUNK",
            slug="search-facet-junk",
            brand=junk_brand,
        )
        product.assign_category(self.category, using="store", set_primary_if_none=True)
        variant = ProductVariant.objects.using("store").create(
            product=product,
            packing="Hộp",
            is_published=True,
            active=True,
            in_stock=1,
        )
        ProductVariantUnit.objects.using("store").create(
            variant=variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=90000,
            is_default=True,
            is_published=True,
        )
        from storeApp.services.product_category_helpers import (
            category_tree_ids,
            product_in_categories_q,
        )

        category_ids = category_tree_ids(self.category, using="store")
        queryset = annotate_variant_unit_price(
            ProductVariant.objects.using("store")
            .filter(active=True, is_published=True, product__active=True)
            .filter(product_in_categories_q(category_ids, using="store"))
            .select_related("product", "product__brand"),
            db_alias="store",
        )
        facets = SearchFacetsService.build_facets(queryset, include_category=False)
        keys = [item["key"] for item in facets["origin_country"]]
        self.assertNotIn("Hộp x 15ml", keys)
        self.assertIn("Việt Nam", keys)


class SearchFacetsCacheTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        cache.clear()

    def test_invalidate_all_cache_bumps_version(self):
        before = SearchFacetsService._cache_version()
        SearchFacetsService.invalidate_all_cache()
        after = SearchFacetsService._cache_version()
        self.assertEqual(after, before + 1)


class SearchFacetsApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.using("store").create(
            slug="search-api-cat",
            name="Search API Cat",
        )
        self.brand = Brand.objects.using("store").create(
            name="Search API Brand",
            country="Pháp",
            active=True,
        )
        self.product = Product.objects.using("store").create(
            name="Search API Product",
            mid="SEARCH-API-001",
            slug="search-api-product",
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

    def test_search_category_returns_brand_and_price_facets(self):
        res = self.client.get(
            f"/api/store/search/?category={self.category.id}&page_size=12"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        facets = body.get("facets") or {}
        self.assertTrue(facets.get("brand"))
        self.assertTrue(facets.get("price_ranges"))

    def test_search_include_facets_false_omits_facet_payload(self):
        res = self.client.get(
            f"/api/store/search/?category={self.category.id}&include_facets=false"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("facets"), {})

    def test_search_origin_country_facet_and_filter(self):
        res = self.client.get(
            f"/api/store/search/?category={self.category.id}&page_size=12"
        )
        self.assertEqual(res.status_code, 200)
        origins = (res.json().get("facets") or {}).get("origin_country") or []
        self.assertTrue(any(o.get("key") == "Pháp" for o in origins))

        filtered = self.client.get(
            f"/api/store/search/?category={self.category.id}&origin_country=Pháp"
        )
        self.assertEqual(filtered.status_code, 200)
        body = filtered.json()
        self.assertEqual(body["meta"]["applied_filters"]["origin_country"], "Pháp")
        self.assertGreaterEqual(body["meta"]["total"], 1)

        junk = self.client.get(
            f"/api/store/search/?category={self.category.id}&origin_country=Hộp%20x%2015ml"
        )
        self.assertEqual(junk.status_code, 200)
        self.assertIsNone(junk.json()["meta"]["applied_filters"]["origin_country"])

    def test_search_multi_brand_filter(self):
        brand_b = Brand.objects.using("store").create(
            name="Search API Brand B",
            country="Việt Nam",
            active=True,
        )
        product_b = Product.objects.using("store").create(
            name="Search API Product B",
            mid="SEARCH-API-002",
            slug="search-api-product-b",
            brand=brand_b,
            category=self.category,
        )
        variant_b = ProductVariant.objects.using("store").create(
            product=product_b,
            packing="Hộp",
            is_published=True,
            active=True,
            in_stock=3,
        )
        ProductVariantUnit.objects.using("store").create(
            variant=variant_b,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=120000,
            is_default=True,
            is_published=True,
        )

        brand_csv = f"{brand_b.id},{self.brand.id}"
        res = self.client.get(
            f"/api/store/search/?category={self.category.id}&brand={brand_csv}"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        applied_brand = body["meta"]["applied_filters"]["brand"]
        self.assertEqual(
            applied_brand,
            ",".join(str(x) for x in sorted([self.brand.id, brand_b.id])),
        )
        self.assertEqual(body["meta"]["total"], 2)

    def test_search_attribute_facets_and_and_or_filter(self):
        from storeApp.models import (
            CatalogAttribute,
            CatalogAttributeOption,
            ProductAttributeValue,
        )

        skin = CatalogAttribute.objects.using("store").create(
            code="skin_type",
            label="Loại da",
            facet_type="multiple",
            sort_order=20,
            is_filterable=True,
        )
        dry = CatalogAttributeOption.objects.using("store").create(
            attribute=skin, slug="da-kho", label="Da khô"
        )
        oily = CatalogAttributeOption.objects.using("store").create(
            attribute=skin, slug="da-dau", label="Da dầu"
        )
        audience = CatalogAttribute.objects.using("store").create(
            code="target_user",
            label="Đối tượng sử dụng",
            facet_type="multiple",
            sort_order=10,
            is_filterable=True,
        )
        adult = CatalogAttributeOption.objects.using("store").create(
            attribute=audience, slug="nguoi-lon", label="Người lớn"
        )

        ProductAttributeValue.objects.using("store").create(
            product=self.product, option=dry
        )
        ProductAttributeValue.objects.using("store").create(
            product=self.product, option=adult
        )

        brand_b = Brand.objects.using("store").create(
            name="Attr Brand B", country="Việt Nam", active=True
        )
        product_b = Product.objects.using("store").create(
            name="Attr Product B",
            mid="SEARCH-API-ATTR-B",
            slug="search-api-attr-b",
            brand=brand_b,
            category=self.category,
        )
        variant_b = ProductVariant.objects.using("store").create(
            product=product_b,
            packing="Hộp",
            is_published=True,
            active=True,
            in_stock=2,
        )
        ProductVariantUnit.objects.using("store").create(
            variant=variant_b,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=99000,
            is_default=True,
            is_published=True,
        )
        ProductAttributeValue.objects.using("store").create(
            product=product_b, option=oily
        )

        res = self.client.get(
            f"/api/store/search/?category={self.category.id}&page_size=12"
        )
        self.assertEqual(res.status_code, 200)
        attrs = (res.json().get("facets") or {}).get("attributes") or []
        codes = [g["code"] for g in attrs]
        self.assertIn("skin_type", codes)
        self.assertIn("target_user", codes)

        # OR within skin_type
        or_res = self.client.get(
            f"/api/store/search/?category={self.category.id}"
            f"&attrs=skin_type:da-kho&attrs=skin_type:da-dau"
        )
        self.assertEqual(or_res.status_code, 200)
        self.assertEqual(or_res.json()["meta"]["total"], 2)

        # AND across codes
        and_res = self.client.get(
            f"/api/store/search/?category={self.category.id}"
            f"&attrs=skin_type:da-kho&attrs=target_user:nguoi-lon"
        )
        self.assertEqual(and_res.status_code, 200)
        body = and_res.json()
        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(
            body["meta"]["applied_filters"]["attrs"],
            ["skin_type:da-kho", "target_user:nguoi-lon"],
        )


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
