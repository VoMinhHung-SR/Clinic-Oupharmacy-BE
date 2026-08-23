from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import Cabinet, CabinetItem, Category, Product, ProductVariant, ProductVariantUnit
from storeApp.models.cabinet import (
    DEFAULT_CABINET_NAME,
    EXPIRED,
    EXPIRING,
    EXPIRING_SOON,
    IN_STOCK,
    LOW_STOCK,
    OUT_OF_STOCK,
    SAFE,
)


class CabinetApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="cabinet-owner@example.com",
            password="test-pass-123",
        )
        self.other = user_model.objects.create_user(
            email="cabinet-other@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(name="Vitamin", slug="vitamin")
        self.product = Product.objects.create(
            name="Vitamin C",
            mid="MID-CAB-001",
            slug="vitamin-c",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp 30 viên",
            sku="CAB-VIT-C",
            in_stock=50,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=30,
            unit_name="Hộp",
            unit_order=0,
            price_value=45000,
            is_default=True,
            is_published=True,
        )
        self.unpublished = ProductVariant.objects.create(
            product=self.product,
            packing="Gói thử",
            sku="CAB-UNPUB",
            in_stock=0,
            is_published=False,
        )
        self.unpublished_unit = ProductVariantUnit.objects.create(
            variant=self.unpublished,
            quantity_in_base=1,
            unit_name="Gói",
            unit_order=0,
            price_value=10000,
            is_default=True,
            is_published=True,
        )

    def _add_item(self, cabinet_id, expiration_date, quantity=10, variant=None, unit=None):
        variant = variant or self.variant
        unit = unit or self.unit
        return self.client.post(
            "/api/store/cabinet-items/",
            {
                "cabinet": cabinet_id,
                "product_variant_id": variant.id,
                "product_variant_unit_id": unit.id,
                "quantity": quantity,
                "expiration_date": expiration_date.isoformat(),
            },
            format="json",
        )

    def test_unauthenticated_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/store/cabinets/")
        self.assertEqual(response.status_code, 401)

    def test_list_auto_creates_default_cabinet(self):
        response = self.client.get("/api/store/cabinets/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], DEFAULT_CABINET_NAME)

        again = self.client.get("/api/store/cabinets/")
        self.assertEqual(len(again.data), 1)
        self.assertEqual(Cabinet.objects.filter(user_id=self.user.id).count(), 1)

    def test_cannot_delete_last_cabinet(self):
        listed = self.client.get("/api/store/cabinets/")
        cabinet_id = listed.data[0]["id"]
        response = self.client.delete(f"/api/store/cabinets/{cabinet_id}/")
        self.assertEqual(response.status_code, 400)

    def test_create_rename_delete_extra_cabinet(self):
        self.client.get("/api/store/cabinets/")
        created = self.client.post(
            "/api/store/cabinets/",
            {"name": "Tủ thuốc bé"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        extra_id = created.data["id"]
        patched = self.client.patch(
            f"/api/store/cabinets/{extra_id}/",
            {"name": "Tủ thuốc cho bé"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.data["name"], "Tủ thuốc cho bé")
        deleted = self.client.delete(f"/api/store/cabinets/{extra_id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(Cabinet.objects.filter(user_id=self.user.id).count(), 1)

    def test_other_user_cannot_access_cabinet(self):
        listed = self.client.get("/api/store/cabinets/")
        cabinet_id = listed.data[0]["id"]
        self.client.force_authenticate(user=self.other)
        response = self.client.get(f"/api/store/cabinets/{cabinet_id}/")
        self.assertEqual(response.status_code, 403)

    def test_add_item_and_qty_zero_out_of_stock(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        today = timezone.now().date()
        created = self._add_item(cabinet_id, today + timedelta(days=200), quantity=10)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["inventory_status"], IN_STOCK)
        self.assertEqual(created.data["expiration_status"], SAFE)
        item_id = created.data["id"]

        patched = self.client.patch(
            f"/api/store/cabinet-items/{item_id}/",
            {"quantity": 0},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.data["inventory_status"], OUT_OF_STOCK)

    def test_unpublished_variant_rejected(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        today = timezone.now().date()
        response = self._add_item(
            cabinet_id,
            today + timedelta(days=100),
            variant=self.unpublished,
            unit=self.unpublished_unit,
        )
        self.assertEqual(response.status_code, 400)

    def test_unit_must_belong_to_variant(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        today = timezone.now().date()
        response = self._add_item(
            cabinet_id,
            today + timedelta(days=100),
            variant=self.variant,
            unit=self.unpublished_unit,
        )
        self.assertEqual(response.status_code, 400)

    def test_expiration_buckets_and_overview(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        today = timezone.now().date()
        expired = self._add_item(cabinet_id, today - timedelta(days=2), quantity=1)
        soon = self._add_item(cabinet_id, today + timedelta(days=10), quantity=2)
        watch = self._add_item(cabinet_id, today + timedelta(days=45), quantity=3)
        safe = self._add_item(cabinet_id, today + timedelta(days=120), quantity=4)
        self.assertEqual(expired.status_code, 201)
        self.assertEqual(expired.data["expiration_status"], EXPIRED)
        self.assertEqual(soon.data["expiration_status"], EXPIRING_SOON)
        self.assertEqual(watch.data["expiration_status"], EXPIRING)
        self.assertEqual(safe.data["expiration_status"], SAFE)

        overview = self.client.get(f"/api/store/cabinets/{cabinet_id}/overview/")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.data["counts"]["total"], 4)
        self.assertEqual(overview.data["counts"]["expired"], 1)
        self.assertEqual(overview.data["counts"]["expiring_soon"], 1)
        self.assertEqual(overview.data["counts"]["expiring"], 1)
        self.assertEqual(len(overview.data["expired"]), 1)
        self.assertEqual(len(overview.data["expiring_soon"]), 1)

        filtered = self.client.get(
            f"/api/store/cabinet-items/?cabinet={cabinet_id}&expiration_status={EXPIRED}"
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(len(filtered.data), 1)
        self.assertEqual(filtered.data[0]["id"], expired.data["id"])

    def test_other_user_cannot_access_item(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        today = timezone.now().date()
        created = self._add_item(cabinet_id, today + timedelta(days=90), quantity=1)
        item_id = created.data["id"]
        self.client.force_authenticate(user=self.other)
        response = self.client.get(f"/api/store/cabinet-items/{item_id}/")
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_add_to_foreign_cabinet(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        self.client.force_authenticate(user=self.other)
        today = timezone.now().date()
        response = self._add_item(cabinet_id, today + timedelta(days=90), quantity=1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CabinetItem.objects.count(), 0)

    def test_low_stock_default_and_custom_threshold(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        today = timezone.now().date()
        default_low = self._add_item(cabinet_id, today + timedelta(days=200), quantity=5)
        in_stock = self._add_item(cabinet_id, today + timedelta(days=200), quantity=6)
        self.assertEqual(default_low.data["inventory_status"], LOW_STOCK)
        self.assertEqual(in_stock.data["inventory_status"], IN_STOCK)

        custom = self.client.post(
            "/api/store/cabinet-items/",
            {
                "cabinet": cabinet_id,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 8,
                "expiration_date": (today + timedelta(days=200)).isoformat(),
                "low_stock_threshold": 10,
            },
            format="json",
        )
        self.assertEqual(custom.status_code, 201)
        self.assertEqual(custom.data["inventory_status"], LOW_STOCK)
        self.assertEqual(custom.data["low_stock_threshold"], 10)

        overview = self.client.get(f"/api/store/cabinets/{cabinet_id}/overview/")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.data["counts"]["low_stock"], 2)
        self.assertEqual(len(overview.data["low_stock"]), 2)

    def test_lot_and_refill_list(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        today = timezone.now().date()
        created = self.client.post(
            "/api/store/cabinet-items/",
            {
                "cabinet": cabinet_id,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 10,
                "expiration_date": (today + timedelta(days=200)).isoformat(),
                "lot_number": "LOT-A1",
                "on_refill_list": True,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["lot_number"], "LOT-A1")
        self.assertTrue(created.data["on_refill_list"])

        overview = self.client.get(f"/api/store/cabinets/{cabinet_id}/overview/")
        self.assertEqual(overview.data["counts"]["on_refill_list"], 1)
        self.assertEqual(overview.data["refill_list"][0]["id"], created.data["id"])

        cleared = self.client.patch(
            f"/api/store/cabinet-items/{created.data['id']}/",
            {"lot_number": "", "on_refill_list": False},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.data["lot_number"])
        self.assertFalse(cleared.data["on_refill_list"])

    def test_settings_change_soon_bucket_and_keep_alerts_visible(self):
        cabinet_id = self.client.get("/api/store/cabinets/").data[0]["id"]
        today = timezone.now().date()
        item = self._add_item(cabinet_id, today + timedelta(days=20), quantity=10)
        self.assertEqual(item.data["expiration_status"], EXPIRING_SOON)

        patched = self.client.patch(
            f"/api/store/cabinets/{cabinet_id}/",
            {"reminder_enabled": False, "expiring_soon_days": 7},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertFalse(patched.data["reminder_enabled"])
        self.assertEqual(patched.data["expiring_soon_days"], 7)

        listed = self.client.get(f"/api/store/cabinet-items/?cabinet={cabinet_id}")
        self.assertEqual(listed.data[0]["expiration_status"], EXPIRING)

        overview = self.client.get(f"/api/store/cabinets/{cabinet_id}/overview/")
        self.assertEqual(overview.status_code, 200)
        self.assertFalse(overview.data["cabinet"]["reminder_enabled"])
        self.assertEqual(overview.data["counts"]["expiring"], 1)
        self.assertEqual(len(overview.data["expired"]), 0)
        self.assertEqual(len(overview.data["expiring_soon"]), 0)
        self.assertIn("low_stock", overview.data)
        self.assertIn("refill_list", overview.data)

