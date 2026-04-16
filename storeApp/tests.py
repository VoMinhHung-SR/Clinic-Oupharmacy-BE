from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import Category, Product, ProductVariant, ProductVariantUnit, SearchKeyword


class SearchKeywordApiTests(APITestCase):
    databases = {"default", "store"}

    def test_record_search_deduplicates_and_increments_hit_count(self):
        first = self.client.post(
            "/api/store/search-terms/",
            {"keyword": "Vitamin"},
            format="json",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            "/api/store/search-terms/",
            {"keyword": "  vItAmIn  "},
            format="json",
        )
        self.assertEqual(second.status_code, 201)

        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(second.data["hit_count"], first.data["hit_count"] + 1)
        self.assertEqual(SearchKeyword.objects.count(), 1)


class SearchSuggestApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.create(name="Thuốc cảm cúm", slug="thuoc-cam-cum")

        for idx in range(6):
            product = Product.objects.create(
                name=f"Sản phẩm cảm cúm {idx}",
                web_name=f"Thuốc trị cảm cúm {idx}",
                slug=f"thuoc-tri-cam-cum-{idx}",
                category=self.category,
            )
            variant = ProductVariant.objects.create(
                product=product,
                packing="Hộp",
                is_published=True,
                in_stock=100 - idx,
                product_ranking=90 - idx,
            )
            ProductVariantUnit.objects.create(
                variant=variant,
                unit_name="Hộp",
                quantity_in_base=1,
                price_value=10000 + idx,
                is_default=True,
                is_published=True,
            )

        kw_1 = SearchKeyword.objects.create(keyword="cảm cúm")
        kw_2 = SearchKeyword.objects.create(keyword="cảm cúm trẻ em")
        SearchKeyword.objects.filter(pk=kw_1.pk).update(
            hit_count=10,
            last_searched_at=timezone.now(),
        )
        SearchKeyword.objects.filter(pk=kw_2.pk).update(
            hit_count=5,
            last_searched_at=timezone.now(),
        )

    def test_search_suggest_returns_expected_groups_and_top5_limit(self):
        response = self.client.get("/api/store/search/suggest/?q=cảm cúm")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["query"], "cảm cúm")

        suggestions = response.data["suggestions"]
        self.assertIn("history_search", suggestions)
        self.assertIn("hot_search", suggestions)
        self.assertIn("categories", suggestions)
        self.assertIn("top_products", suggestions)

        self.assertGreaterEqual(len(suggestions["history_search"]), 1)
        self.assertGreaterEqual(len(suggestions["hot_search"]), 1)
        self.assertGreaterEqual(len(suggestions["categories"]), 1)
        self.assertGreaterEqual(len(suggestions["top_products"]), 1)
        self.assertLessEqual(len(suggestions["top_products"]), 5)
