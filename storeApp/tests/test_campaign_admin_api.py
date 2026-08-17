"""Admin Campaign API tests (P1-T3)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import Campaign, CampaignCategory, CampaignPlacement, CampaignProduct, Voucher


class CampaignAdminApiTests(APITestCase):
    databases = {"default", "store"}
    base = "/api/store/admin/campaigns/"

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.staff = User.objects.create_user(
            email="campaign-admin@example.com",
            password="test-pass-123",
        )
        self.staff.is_staff = True
        self.staff.is_superuser = True
        self.staff.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_authenticate(user=self.staff)
        now = timezone.now()
        self.window = {
            "start_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "end_at": (now + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        }

    def test_unauthenticated_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(self.base)
        self.assertEqual(res.status_code, 401)

    def test_staff_without_perm_403(self):
        User = get_user_model()
        plain = User.objects.create_user(
            email="campaign-staff-noperm@example.com",
            password="test-pass-123",
            is_staff=True,
            is_superuser=False,
            is_admin=False,
        )
        self.client.force_authenticate(user=plain)
        res = self.client.get(self.base)
        self.assertEqual(res.status_code, 403)

    def test_business_admin_without_staff_200(self):
        User = get_user_model()
        biz = User.objects.create_user(
            email="campaign-biz-admin@example.com",
            password="test-pass-123",
            is_admin=True,
            is_staff=False,
            is_superuser=False,
        )
        self.client.force_authenticate(user=biz)
        res = self.client.get(self.base)
        self.assertEqual(res.status_code, 200)

    def test_create_list_detail_patch_publish_placements(self):
        create = self.client.post(
            self.base,
            {
                "name": "Ops Tet",
                "slug": "tet-2027",
                "title": "Tết 2027",
                **self.window,
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        self.assertEqual(create.data["status"], "draft")
        cid = create.data["id"]
        version = create.data["version"]

        listing = self.client.get(self.base)
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(any(row["id"] == cid for row in listing.data))

        detail = self.client.get(f"{self.base}{cid}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["slug"], "tet-2027")

        patch_conflict = self.client.patch(
            f"{self.base}{cid}/",
            {"version": version + 9, "title": "Nope"},
            format="json",
        )
        self.assertEqual(patch_conflict.status_code, 409)
        self.assertEqual(patch_conflict.data["code"], "version_conflict")

        patch_ok = self.client.patch(
            f"{self.base}{cid}/",
            {"version": version, "title": "Tết updated"},
            format="json",
        )
        self.assertEqual(patch_ok.status_code, 200, patch_ok.data)
        self.assertEqual(patch_ok.data["title"], "Tết updated")
        version = patch_ok.data["version"]

        placements = self.client.put(
            f"{self.base}{cid}/placements/",
            {
                "version": version,
                "placements": [
                    {
                        "slot": "HOME_HERO",
                        "title": "Hero",
                        "cta_url": "/khuyen-mai/tet-2027",
                        "sort_order": 0,
                        "is_enabled": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(placements.status_code, 200, placements.data)
        self.assertEqual(len(placements.data["placements"]), 1)
        version = placements.data["version"]

        publish = self.client.post(
            f"{self.base}{cid}/publish/",
            {"version": version},
            format="json",
        )
        self.assertEqual(publish.status_code, 200, publish.data)
        self.assertEqual(publish.data["status"], "active")

        campaign = Campaign.objects.get(id=cid)
        self.assertEqual(campaign.placements.count(), 1)

    def test_replace_products_and_categories(self):
        create = self.client.post(
            self.base,
            {
                "name": "Scope Ops",
                "slug": "scope-ops",
                "title": "Scope",
                **self.window,
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        cid = create.data["id"]
        version = create.data["version"]

        products = self.client.put(
            f"{self.base}{cid}/products/",
            {"version": version, "product_mids": ["MID001", "MID002", "MID001", "  "]},
            format="json",
        )
        self.assertEqual(products.status_code, 200, products.data)
        self.assertEqual(products.data["product_mids"], ["MID001", "MID002"])
        version = products.data["version"]

        categories = self.client.put(
            f"{self.base}{cid}/categories/",
            {
                "version": version,
                "category_slugs": ["duoc-my-pham", "duoc-my-pham", "thuc-pham-chuc-nang"],
            },
            format="json",
        )
        self.assertEqual(categories.status_code, 200, categories.data)
        self.assertEqual(
            categories.data["category_slugs"],
            ["duoc-my-pham", "thuc-pham-chuc-nang"],
        )
        version = categories.data["version"]

        conflict = self.client.put(
            f"{self.base}{cid}/products/",
            {"version": version - 1, "product_mids": ["MID999"]},
            format="json",
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "version_conflict")

        clear = self.client.put(
            f"{self.base}{cid}/products/",
            {"version": version, "product_mids": []},
            format="json",
        )
        self.assertEqual(clear.status_code, 200, clear.data)
        self.assertEqual(clear.data["product_mids"], [])

    def test_replace_vouchers(self):
        live = Voucher.objects.create(
            code="CAMP10",
            type="PERCENT",
            value="10.00",
            description="Camp 10%",
            is_active=True,
        )
        dead = Voucher.objects.create(
            code="DEAD10",
            type="PERCENT",
            value="10.00",
            is_active=False,
        )
        create = self.client.post(
            self.base,
            {
                "name": "Voucher Ops",
                "slug": "voucher-ops",
                "title": "Voucher Ops",
                **self.window,
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        cid = create.data["id"]
        version = create.data["version"]

        bad = self.client.put(
            f"{self.base}{cid}/vouchers/",
            {"version": version, "vouchers": [{"voucher_id": 999999}]},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)

        ok = self.client.put(
            f"{self.base}{cid}/vouchers/",
            {
                "version": version,
                "vouchers": [
                    {"voucher_id": live.id, "sort_order": 0, "is_featured": True},
                    {"voucher_id": dead.id, "sort_order": 1, "is_featured": False},
                    {"voucher_id": live.id, "sort_order": 2},
                ],
            },
            format="json",
        )
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(ok.data["voucher_ids"], [live.id, dead.id])
