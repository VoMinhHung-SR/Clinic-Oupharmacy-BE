"""Admin Campaign API tests (P1-T3)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import Campaign


class CampaignAdminApiTests(APITestCase):
    databases = {"default", "store"}
    base = "/api/store/admin/campaigns/"

    def setUp(self):
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
        )
        self.client.force_authenticate(user=plain)
        res = self.client.get(self.base)
        self.assertEqual(res.status_code, 403)

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
