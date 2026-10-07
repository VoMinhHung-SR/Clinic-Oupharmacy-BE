"""Lightweight product sitemap feed for storefront SEO."""
from rest_framework.test import APITestCase

from storeApp.models import Category, Product


class CatalogSitemapFeedTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.using("store").create(
            slug="sitemap-cat",
            name="Sitemap Cat",
            path_slug="sitemap-cat",
        )
        self.product = Product.objects.using("store").create(
            name="Sitemap Feed Product",
            mid="SITEMAP-FEED-001",
            slug="sitemap-feed-product",
            active=True,
        )
        self.product.assign_category(self.category, using="store", set_primary_if_none=True)

    def test_sitemap_feed_returns_slug_path_and_200(self):
        response = self.client.get("/api/store/products/sitemap/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("results", body)
        paths = {row["path"] for row in body["results"]}
        self.assertIn("sitemap-cat/sitemap-feed-product", paths)
        match = next(
            row for row in body["results"] if row["path"] == "sitemap-cat/sitemap-feed-product"
        )
        self.assertEqual(match["slug"], "sitemap-feed-product")
        self.assertIn("updated_at", match)
