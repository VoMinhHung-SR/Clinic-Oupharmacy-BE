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

    def test_ensure_unit_pricing_consult_keeps_display_fills_value(self):
        from storeApp.management.commands.catalog_import.store_import_pricing import (
            PRICE_DISPLAY_CONSULT,
            ensure_unit_pricing,
        )

        random.seed(7)
        units = [
            {
                "unit_name": "Hộp",
                "quantity_in_base": 30,
                "price_value": 0,
                "price_display": "CONSULT",
                "is_default": True,
            }
        ]
        ensure_unit_pricing(units, fallback_price=0, use_smart_random=True)
        self.assertGreater(units[0]["price_value"], 0)
        self.assertEqual(units[0]["price_display"], PRICE_DISPLAY_CONSULT)
        self.assertNotIn("scrape_was_consult", units[0])

    def test_ensure_unit_pricing_preserves_manual_ref_clinic_value(self):
        from storeApp.management.commands.catalog_import.store_import_pricing import (
            PRICE_DISPLAY_CONSULT,
            ensure_unit_pricing,
            force_consult_storefront_on_units,
            row_uses_consult_storefront,
        )

        units = [
            {
                "unit_name": "Hộp",
                "quantity_in_base": 30,
                "price_value": 600000,
                "price_display": "600.000đ / Hộp",
                "is_default": True,
            }
        ]
        row = {
            "import.scrapePriceGap": "consult",
            "import.priceSource": "manual_ref_p3",
            "pricing.priceDisplay": "600.000đ / Hộp",
            "pricing.priceValue": "600000",
        }
        ensure_unit_pricing(units, fallback_price=600000, fallback_display="600.000đ / Hộp")
        self.assertTrue(row_uses_consult_storefront(row))
        force_consult_storefront_on_units(units)
        self.assertEqual(units[0]["price_value"], 600000.0)
        self.assertEqual(units[0]["price_display"], PRICE_DISPLAY_CONSULT)

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

    def test_parse_packing_hierarchy_hop_vi_vien(self):
        from storeApp.management.commands.catalog_import.store_import_packaging import (
            parse_packing_hierarchy,
            expand_sale_units_from_pack_price,
        )

        levels = parse_packing_hierarchy("Hộp 3 Vỉ x 10 Viên")
        self.assertEqual(
            [(x["unit_name"], x["quantity_in_base"]) for x in levels],
            [("Viên", 1), ("Vỉ", 10), ("Hộp", 30)],
        )
        units = expand_sale_units_from_pack_price("Hộp 3 Vỉ x 10 Viên", 105000)
        by_name = {u["unitName"]: u for u in units}
        self.assertEqual(by_name["Viên"]["priceValue"], 3500.0)
        self.assertEqual(by_name["Vỉ"]["priceValue"], 35000.0)
        self.assertEqual(by_name["Hộp"]["priceValue"], 105000.0)
        self.assertEqual(by_name["Hộp"]["quantityInBase"], 30)
        self.assertTrue(by_name["Hộp"]["isDefault"])
        self.assertFalse(by_name["Viên"]["isDefault"])

    def test_reconcile_sale_units_expands_single_hop(self):
        from storeApp.management.commands.catalog_import.store_import_packaging import (
            reconcile_sale_units_with_packing,
        )
        from storeApp.management.commands.catalog_import.store_import_row import (
            build_variant_payloads_from_sale_units,
        )

        raw = [
            {
                "unitName": "Hộp",
                "quantityInBase": 1,
                "unitOrder": 0,
                "isDefault": True,
                "priceValue": 105000,
                "priceDisplay": "105.000đ",
            }
        ]
        expanded = reconcile_sale_units_with_packing(raw, "Hộp 3 Vỉ x 10 Viên")
        self.assertEqual(len(expanded), 3)
        payloads = build_variant_payloads_from_sale_units(raw, "Hộp 3 Vỉ x 10 Viên")
        units = payloads[0]["units"]
        self.assertEqual(payloads[0]["base_unit"], "Viên")
        self.assertEqual(len(units), 3)
        hop = next(u for u in units if u["unit_name"] == "Hộp")
        self.assertEqual(hop["quantity_in_base"], 30)
        self.assertEqual(hop["price_value"], 105000.0)

    def test_reconcile_consult_keeps_clinic_value_and_consult_display(self):
        from storeApp.management.commands.catalog_import.store_import_packaging import (
            reconcile_sale_units_with_packing,
        )
        from storeApp.management.commands.catalog_import.store_import_pricing import (
            PRICE_DISPLAY_CONSULT,
            ensure_unit_pricing,
        )
        from storeApp.management.commands.catalog_import.store_import_row import (
            build_variant_payloads_from_sale_units,
        )

        raw = [
            {
                "unitName": "Hộp",
                "quantityInBase": 1,
                "unitOrder": 0,
                "isDefault": True,
                "priceValue": 105000,
                "priceDisplay": "CONSULT",
            }
        ]
        payloads = build_variant_payloads_from_sale_units(raw, "Hộp 3 Vỉ x 10 Viên")
        units = payloads[0]["units"]
        ensure_unit_pricing(units, fallback_price=0, use_smart_random=False)
        hop = next(u for u in units if u["unit_name"] == "Hộp")
        self.assertEqual(hop["price_value"], 105000.0)
        self.assertEqual(hop["price_display"], PRICE_DISPLAY_CONSULT)
        # Expanded levels keep proportional clinic values
        vien = next(u for u in units if u["unit_name"] == "Viên")
        self.assertEqual(vien["price_value"], 3500.0)
        self.assertEqual(vien["price_display"], PRICE_DISPLAY_CONSULT)

    def test_parse_packing_hop_one_vi_collapses_duplicate(self):
        from storeApp.management.commands.catalog_import.store_import_packaging import (
            parse_packing_hierarchy,
            expand_sale_units_from_pack_price,
        )

        # Hộp 1 Vỉ x 4 Viên → skip duplicate Vỉ/Hộp (same qib)
        levels = parse_packing_hierarchy("Hộp 1 Vỉ x 4 Viên")
        self.assertEqual(
            [(x["unit_name"], x["quantity_in_base"]) for x in levels],
            [("Viên", 1), ("Hộp", 4)],
        )
        units = expand_sale_units_from_pack_price("Hộp 1 Vỉ x 4 Viên", 170000)
        by_name = {u["unitName"]: u for u in units}
        self.assertEqual(set(by_name), {"Viên", "Hộp"})
        self.assertEqual(by_name["Viên"]["priceValue"], 42500.0)
        self.assertEqual(by_name["Hộp"]["priceValue"], 170000.0)
        self.assertEqual(by_name["Hộp"]["quantityInBase"], 4)

    def test_parse_packing_hop_n_vien_not_vi(self):
        from storeApp.management.commands.catalog_import.store_import_packaging import (
            parse_packing_hierarchy,
            expand_sale_units_from_pack_price,
        )

        levels = parse_packing_hierarchy("Hộp 60 Viên")
        self.assertEqual(
            [(x["unit_name"], x["quantity_in_base"]) for x in levels],
            [("Viên", 1), ("Hộp", 60)],
        )
        units = expand_sale_units_from_pack_price("Hộp 60 Viên", 355000)
        by_name = {u["unitName"]: u for u in units}
        self.assertEqual(by_name["Viên"]["priceValue"], 5917.0)
        self.assertEqual(by_name["Hộp"]["priceValue"], 355000.0)


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
