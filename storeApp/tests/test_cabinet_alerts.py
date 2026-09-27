from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import (
    Cabinet,
    CabinetAlert,
    CabinetItem,
    Category,
    Product,
    ProductVariant,
    ProductVariantUnit,
)
from storeApp.models.cabinet import ALERT_EXPIRED, ALERT_EXPIRING_SOON
from storeApp.services.cabinet_alert_scan import scan_cabinet_expiry_alerts


class CabinetAlertTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="cabinet-alert-owner@example.com",
            password="test-pass-123",
        )
        self.other = user_model.objects.create_user(
            email="cabinet-alert-other@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        category = Category.objects.create(name="Alert Vitamin", slug="alert-vitamin")
        product = Product.objects.create(
            name="Alert Vitamin C",
            mid="MID-ALERT-001",
            slug="alert-vitamin-c",
            category=category,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp 30 viên",
            sku="ALERT-VIT-C",
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
        self.cabinet = Cabinet.objects.create(
            user_id=self.user.id,
            name="Tủ alert",
            reminder_enabled=True,
            expiring_soon_days=30,
        )
        today = timezone.now().date()
        self.soon_item = CabinetItem.objects.create(
            cabinet=self.cabinet,
            product_variant=self.variant,
            product_variant_unit=self.unit,
            quantity=5,
            expiration_date=today + timedelta(days=10),
        )
        self.expired_item = CabinetItem.objects.create(
            cabinet=self.cabinet,
            product_variant=self.variant,
            product_variant_unit=self.unit,
            quantity=2,
            expiration_date=today - timedelta(days=2),
        )
        self.safe_item = CabinetItem.objects.create(
            cabinet=self.cabinet,
            product_variant=self.variant,
            product_variant_unit=self.unit,
            quantity=3,
            expiration_date=today + timedelta(days=120),
        )

    def test_scan_creates_expiring_and_expired_alerts(self):
        result = scan_cabinet_expiry_alerts()
        self.assertEqual(result["created"], 2)
        kinds = set(CabinetAlert.objects.filter(user_id=self.user.id).values_list("kind", flat=True))
        self.assertEqual(kinds, {ALERT_EXPIRING_SOON, ALERT_EXPIRED})

    def test_scan_dedupes_same_item_kind(self):
        first = scan_cabinet_expiry_alerts()
        second = scan_cabinet_expiry_alerts()
        self.assertEqual(first["created"], 2)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["skipped_dedupe"], 2)
        self.assertEqual(CabinetAlert.objects.filter(user_id=self.user.id).count(), 2)

    def test_scan_skips_when_reminder_disabled(self):
        self.cabinet.reminder_enabled = False
        self.cabinet.save(update_fields=["reminder_enabled", "updated_date"])
        result = scan_cabinet_expiry_alerts()
        self.assertEqual(result["created"], 0)
        self.assertEqual(CabinetAlert.objects.filter(user_id=self.user.id).count(), 0)

    def test_list_owner_only_and_mark_read(self):
        scan_cabinet_expiry_alerts()
        CabinetAlert.objects.create(
            user_id=self.other.id,
            cabinet_item=None,
            kind=ALERT_EXPIRED,
            title="Other alert",
            body="secret",
            is_read=False,
        )

        response = self.client.get("/api/store/cabinet-alerts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        for row in response.data:
            self.assertNotEqual(row["title"], "Other alert")

        unread = self.client.get("/api/store/cabinet-alerts/?unread=1")
        self.assertEqual(len(unread.data), 2)

        alert_id = response.data[0]["id"]
        marked = self.client.post(f"/api/store/cabinet-alerts/{alert_id}/mark-read/")
        self.assertEqual(marked.status_code, 200)
        self.assertTrue(marked.data["is_read"])

        unread_after = self.client.get("/api/store/cabinet-alerts/?unread=1")
        self.assertEqual(len(unread_after.data), 1)

    def test_other_user_cannot_mark_read(self):
        scan_cabinet_expiry_alerts()
        alert = CabinetAlert.objects.filter(user_id=self.user.id).first()
        self.client.force_authenticate(user=self.other)
        response = self.client.post(f"/api/store/cabinet-alerts/{alert.id}/mark-read/")
        self.assertEqual(response.status_code, 403)

    def test_dismiss_removes_from_list_and_blocks_recreate(self):
        scan_cabinet_expiry_alerts()
        listed = self.client.get("/api/store/cabinet-alerts/")
        self.assertEqual(len(listed.data), 2)
        alert_id = listed.data[0]["id"]

        dismissed = self.client.post(f"/api/store/cabinet-alerts/{alert_id}/dismiss/")
        self.assertEqual(dismissed.status_code, 200)
        self.assertEqual(dismissed.data["dismissed"], alert_id)

        after = self.client.get("/api/store/cabinet-alerts/")
        self.assertEqual(len(after.data), 1)
        self.assertNotEqual(after.data[0]["id"], alert_id)

        rescan = scan_cabinet_expiry_alerts()
        self.assertEqual(rescan["created"], 0)
        self.assertGreaterEqual(rescan["skipped_dismissed"], 1)
        self.assertEqual(
            CabinetAlert.objects.filter(user_id=self.user.id, active=True).count(),
            1,
        )

    def test_other_user_cannot_dismiss(self):
        scan_cabinet_expiry_alerts()
        alert = CabinetAlert.objects.filter(user_id=self.user.id).first()
        self.client.force_authenticate(user=self.other)
        response = self.client.post(f"/api/store/cabinet-alerts/{alert.id}/dismiss/")
        self.assertEqual(response.status_code, 403)

    def test_clear_read_only_clears_read_alerts(self):
        scan_cabinet_expiry_alerts()
        listed = self.client.get("/api/store/cabinet-alerts/")
        first_id = listed.data[0]["id"]
        self.client.post(f"/api/store/cabinet-alerts/{first_id}/mark-read/")

        cleared = self.client.post("/api/store/cabinet-alerts/clear-read/")
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.data["cleared"], 1)

        remaining = self.client.get("/api/store/cabinet-alerts/")
        self.assertEqual(len(remaining.data), 1)
        self.assertFalse(remaining.data[0]["is_read"])

    def test_scan_caps_alerts_per_user(self):
        from storeApp.services import cabinet_alert_scan as scan_mod

        today = timezone.now().date()
        for i in range(12):
            CabinetItem.objects.create(
                cabinet=self.cabinet,
                product_variant=self.variant,
                product_variant_unit=self.unit,
                quantity=1,
                expiration_date=today - timedelta(days=1 + i),
            )
        # soon + expired already in setUp (2) + 12 expired = 14 candidates
        previous = scan_mod.MAX_ALERTS_PER_USER_PER_SCAN
        scan_mod.MAX_ALERTS_PER_USER_PER_SCAN = 10
        try:
            result = scan_cabinet_expiry_alerts()
            self.assertEqual(result["created"], 10)
            self.assertGreaterEqual(result["skipped_cap"], 1)
            self.assertEqual(
                CabinetAlert.objects.filter(user_id=self.user.id, active=True).count(),
                10,
            )
        finally:
            scan_mod.MAX_ALERTS_PER_USER_PER_SCAN = previous
