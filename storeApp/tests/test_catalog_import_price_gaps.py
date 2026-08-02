"""Unit tests for import skip + scrape price-gap classification (no DB)."""

import unittest

from storeApp.management.commands.catalog_import.store_import_pricing import (
    PRICE_DISPLAY_CONSULT,
    classify_unit_scrape_price_gap,
    collect_unit_price_gaps,
    mark_scrape_consult_unit,
    row_uses_consult_storefront,
)
from storeApp.management.commands.catalog_import.store_import_skip import (
    should_skip_category_array,
)


class ImportSkipTests(unittest.TestCase):
    def test_skip_cloudflare_5xx_landing(self):
        self.assertTrue(
            should_skip_category_array(
                [{"name": "cloudflare.com", "slug": "5xx-error-landing"}]
            )
        )

    def test_keep_normal_l0(self):
        self.assertFalse(
            should_skip_category_array([{"name": "Thuốc", "slug": "thuoc"}])
        )


class ScrapePriceGapTests(unittest.TestCase):
    def test_consult_marked(self):
        unit = {"unit_name": "Hộp", "price_value": 0, "price_display": None}
        mark_scrape_consult_unit(unit)
        self.assertEqual(classify_unit_scrape_price_gap(unit), "consult")

    def test_zero_and_missing(self):
        self.assertEqual(
            classify_unit_scrape_price_gap(
                {"unit_name": "Hộp", "price_value": 0, "price_display": ""}
            ),
            "zero",
        )
        self.assertEqual(
            classify_unit_scrape_price_gap(
                {"unit_name": "Hộp", "price_value": None, "price_display": None}
            ),
            "missing",
        )

    def test_positive_ok(self):
        self.assertIsNone(
            classify_unit_scrape_price_gap(
                {"unit_name": "Hộp", "price_value": 120000, "price_display": "120.000đ"}
            )
        )

    def test_collect_gaps(self):
        units = [
            {"unit_name": "Hộp", "price_value": 0, "price_display": "CONSULT"},
            {"unit_name": "Vỉ", "price_value": 5000, "price_display": "5.000đ"},
        ]
        gaps = collect_unit_price_gaps(units)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0][1], "consult")

    def test_row_uses_consult_storefront(self):
        self.assertTrue(
            row_uses_consult_storefront({"import.scrapePriceGap": "consult"})
        )
        self.assertTrue(
            row_uses_consult_storefront({"pricing.priceDisplay": "CONSULT"})
        )
        self.assertTrue(
            row_uses_consult_storefront({"import.priceSource": "manual_ref_batch_012"})
        )
        self.assertFalse(
            row_uses_consult_storefront(
                {
                    "pricing.priceDisplay": "120.000đ",
                    "import.priceSource": "scrape",
                }
            )
        )
        self.assertEqual(PRICE_DISPLAY_CONSULT, "CONSULT")


if __name__ == "__main__":
    unittest.main()
