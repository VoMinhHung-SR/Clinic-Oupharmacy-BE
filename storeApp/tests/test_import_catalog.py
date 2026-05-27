"""Catalog CSV import helpers and multi-category merge on Product."""
import random
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

class StoreImportCsvHelperTests(SimpleTestCase):
    def test_parse_sale_units_from_csv_json_string(self):
        from storeApp.management.commands.catalog_import.store_import_row import (
            build_variant_payloads_from_sale_units as _build_variant_payloads_from_sale_units,
            parse_json_field as _parse_json_field,
        )

        raw = (
            '[{"unitName":"Hộp","quantityInBase":120,"unitOrder":0,'
            '"isDefault":true,"priceValue":330000,"priceDisplay":"330.000đ / Hộp"}]'
        )
        sale_units = _parse_json_field(raw, default=[])
        self.assertEqual(len(sale_units), 1)
        payloads = _build_variant_payloads_from_sale_units(sale_units, "Hộp x 120")
        self.assertEqual(payloads[0]["units"][0]["quantity_in_base"], 120)
        self.assertEqual(payloads[0]["units"][0]["price_value"], 330000.0)

    def test_ensure_unit_pricing_uses_row_fallback_before_random(self):
        from storeApp.management.commands.catalog_import.store_import_pricing import ensure_unit_pricing

        units = [
            {
                "unit_name": "Hộp",
                "quantity_in_base": 40,
                "price_value": 0,
                "price_display": None,
                "is_default": True,
            }
        ]
        ensure_unit_pricing(units, fallback_price=400000, fallback_display="400.000đ / Hộp")
        self.assertEqual(units[0]["price_value"], 400000.0)

    def test_smart_random_scales_with_quantity_in_base(self):
        from storeApp.management.commands.catalog_import.store_import_pricing import smart_random_unit_price

        random.seed(42)
        hop = smart_random_unit_price("Hộp", 40)
        vien = smart_random_unit_price("Viên", 1)
        self.assertGreaterEqual(hop, 40_000)
        self.assertLessEqual(vien, 15_000)
        self.assertGreater(hop, vien)

    def test_infer_sibling_price_for_zero_unit(self):
        from storeApp.management.commands.catalog_import.store_import_pricing import ensure_unit_pricing

        units = [
            {"unit_name": "Viên", "quantity_in_base": 1, "price_value": 5000, "is_default": False},
            {"unit_name": "Hộp", "quantity_in_base": 40, "price_value": 0, "is_default": True},
        ]
        ensure_unit_pricing(units, fallback_price=0, use_smart_random=False)
        self.assertEqual(units[1]["price_value"], 200000.0)

    def test_batch_quantity_scales_with_quantity_in_base(self):
        from storeApp.management.commands.catalog_import.store_import_row import compute_synthetic_batch_quantity

        qty = compute_synthetic_batch_quantity(40, 10, 10)
        self.assertEqual(qty, 400)

    def test_import_price_per_base_unit_from_sale_unit(self):
        from storeApp.management.commands.catalog_import.store_import_row import compute_import_price_per_base_unit

        price = compute_import_price_per_base_unit(425000, 40)
        self.assertEqual(price, Decimal("10625.00"))


class StoreImportCategoryMergeTests(TestCase):
    databases = {"default", "store"}

    def test_assign_category_merges_without_replacing_primary(self):
        from storeApp.models import Category, Product, ProductCategory

        root_a, _ = Category.objects.using("store").get_or_create(
            slug="cat-a", parent=None, defaults={"name": "Cat A"}
        )
        leaf_a, _ = Category.objects.using("store").get_or_create(
            slug="leaf-a", parent=root_a, defaults={"name": "Leaf A"}
        )
        root_b, _ = Category.objects.using("store").get_or_create(
            slug="cat-b", parent=None, defaults={"name": "Cat B"}
        )
        leaf_b, _ = Category.objects.using("store").get_or_create(
            slug="leaf-b", parent=root_b, defaults={"name": "Leaf B"}
        )

        product = Product.objects.using("store").create(
            name="Multi-cat test product",
            mid="TEST-MULTI-CAT-001",
            slug="multi-cat-test-product",
        )
        product.assign_category(leaf_a, using="store", set_primary_if_none=True)
        product.refresh_from_db(using="store")
        self.assertEqual(product.category_id, leaf_a.id)

        product.assign_category(leaf_b, using="store", set_primary_if_none=True)
        product.refresh_from_db(using="store")
        self.assertEqual(product.category_id, leaf_a.id)

        links = list(
            ProductCategory.objects.using("store")
            .filter(product=product)
            .values_list("category_id", "is_primary")
        )
        self.assertEqual(len(links), 2)
        self.assertIn((leaf_a.id, True), links)
        self.assertIn((leaf_b.id, False), links)
