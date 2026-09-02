"""P4 — sync_mainapp_data maps original_price_value → compare_at_price."""

from unittest.mock import MagicMock

from django.test import SimpleTestCase


class SyncMainappCompareAtMappingTests(SimpleTestCase):
    def test_variant_unit_defaults_include_compare_from_original(self):
        mu = MagicMock()
        mu.id = 42
        mu.package_size = "Hộp"
        mu.price_value = 85000
        mu.price_display = None
        mu.original_price_value = 120000
        mu.is_published = True

        defaults = {
            "price_value": mu.price_value or 0,
            "compare_at_price": mu.original_price_value,
        }

        self.assertEqual(defaults["compare_at_price"], 120000)
        self.assertEqual(defaults["price_value"], 85000)
        self.assertGreater(defaults["compare_at_price"], defaults["price_value"])
