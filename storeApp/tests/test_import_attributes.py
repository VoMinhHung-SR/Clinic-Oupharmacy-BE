"""Unit tests for catalog attribute import skeleton (no DB network facets)."""
from django.test import SimpleTestCase, TestCase

from storeApp.management.commands.catalog_import.store_import_attributes import (
    attribute_option_slug,
    collect_attribute_labels_from_row,
    upsert_product_attributes_from_row,
)
from storeApp.models import (
    Brand,
    CatalogAttribute,
    CatalogAttributeOption,
    Category,
    Product,
    ProductAttributeValue,
)
from storeApp.services.catalog_attribute_map import SOURCE_TO_STORE_ATTR


class AttributeSlugTests(SimpleTestCase):
    def test_vietnamese_slug(self):
        self.assertEqual(attribute_option_slug("Da khô"), "da-kho")
        self.assertEqual(attribute_option_slug("Viên ngậm"), "vien-ngam")
        self.assertEqual(attribute_option_slug("Vị Cam"), "vi-cam")


class CollectAttributeLabelsTests(SimpleTestCase):
    def test_nested_attributes_blob(self):
        row = {
            "attributes": {
                "objectUse": ["Người lớn", "Trẻ em"],
                "skin": ["Da khô"],
                "dosageForm": "Gel",
                "brandOrigin": "Pháp",
                "brand": "ShouldSkip",
            }
        }
        got = collect_attribute_labels_from_row(row)
        self.assertEqual(got["target_user"], ["Người lớn", "Trẻ em"])
        self.assertEqual(got["skin_type"], ["Da khô"])
        self.assertEqual(got["dosage_form"], ["Gel"])
        self.assertEqual(got["brand_origin"], ["Pháp"])
        self.assertNotIn("brand", got)

    def test_flat_pdp_fields(self):
        row = {
            "objectUse": '["Phụ nữ"]',
            "product.brandOrigin": "Pháp",
            "indications": ["Mụn"],
        }
        got = collect_attribute_labels_from_row(row)
        self.assertEqual(got["target_user"], ["Phụ nữ"])
        self.assertEqual(got["brand_origin"], ["Pháp"])
        self.assertEqual(got["indication"], ["Mụn"])

    def test_source_map_covers_spike_codes(self):
        for code in ("objectUse", "skin", "flavor", "indications", "dosageForm", "brandOrigin"):
            self.assertIn(code, SOURCE_TO_STORE_ATTR)


class UpsertProductAttributesDbTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.brand = Brand.objects.using("store").create(name="Attr Import Brand", country="Việt Nam")
        self.category = Category.objects.using("store").create(
            slug="attr-import-cat", name="Attr Import Cat"
        )
        self.product = Product.objects.using("store").create(
            name="Attr Import Product",
            mid="ATTR-IMPORT-001",
            slug="attr-import-product",
            brand=self.brand,
            category=self.category,
        )
        CatalogAttribute.objects.using("store").create(
            code="skin_type",
            label="Loại da",
            facet_type="multiple",
            sort_order=20,
            is_filterable=True,
        )
        CatalogAttribute.objects.using("store").create(
            code="dosage_form",
            label="Dạng bào chế",
            facet_type="multiple",
            sort_order=50,
            is_filterable=True,
        )

    def test_upsert_creates_options_and_values(self):
        stats = upsert_product_attributes_from_row(
            self.product,
            {"attributes": {"skin": ["Da dầu"], "dosageForm": "Kem"}},
            dry_run=False,
            using="store",
        )
        self.assertEqual(stats["attribute_values_created"], 2)
        self.assertEqual(stats["attribute_options_created"], 2)
        self.assertTrue(
            ProductAttributeValue.objects.using("store")
            .filter(product=self.product, option__slug="da-dau")
            .exists()
        )
        self.assertTrue(
            CatalogAttributeOption.objects.using("store")
            .filter(attribute__code="dosage_form", slug="kem")
            .exists()
        )

        # Idempotent
        stats2 = upsert_product_attributes_from_row(
            self.product,
            {"attributes": {"skin": ["Da dầu"], "dosageForm": "Kem"}},
            dry_run=False,
            using="store",
        )
        self.assertEqual(stats2["attribute_values_created"], 0)
        self.assertEqual(stats2["attribute_values_existing"], 2)
