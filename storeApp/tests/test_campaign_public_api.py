"""Public campaign API tests (P2-T1)."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import Campaign, CampaignPlacement


class CampaignPublicApiTests(APITestCase):
    databases = {"default", "store"}
    base = "/api/store/campaigns/"

    def _create_campaign(self, *, slug, status, priority=0, start_delta=-1, end_delta=48, title=None):
        now = timezone.now()
        return Campaign.objects.create(
            name=f"ops-{slug}",
            slug=slug,
            title=title or slug,
            status=status,
            priority=priority,
            start_at=now + timedelta(hours=start_delta),
            end_at=now + timedelta(hours=end_delta),
        )

    def test_draft_not_in_list_and_404_detail(self):
        draft = self._create_campaign(slug="draft-hide", status=Campaign.STATUS_DRAFT)
        active = self._create_campaign(slug="live-show", status=Campaign.STATUS_ACTIVE)

        listing = self.client.get(self.base)
        self.assertEqual(listing.status_code, 200)
        slugs = {row["slug"] for row in listing.data}
        self.assertIn("live-show", slugs)
        self.assertNotIn("draft-hide", slugs)

        missing = self.client.get(f"{self.base}{draft.slug}/")
        self.assertEqual(missing.status_code, 404)
        # Same shape as unknown slug (no status leak).
        unknown = self.client.get(f"{self.base}does-not-exist/")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(missing.data, unknown.data)

        ok = self.client.get(f"{self.base}{active.slug}/")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["slug"], "live-show")
        self.assertEqual(ok.data["product_mids"], [])
        self.assertEqual(ok.data["vouchers"], [])

    def test_placements_winner_by_priority_and_null_slots(self):
        low = self._create_campaign(slug="low-prio", status=Campaign.STATUS_ACTIVE, priority=1)
        high = self._create_campaign(slug="high-prio", status=Campaign.STATUS_ACTIVE, priority=100)
        CampaignPlacement.objects.create(
            campaign=low,
            slot=CampaignPlacement.SLOT_HOME_HERO,
            title="Low hero",
            is_enabled=True,
        )
        CampaignPlacement.objects.create(
            campaign=high,
            slot=CampaignPlacement.SLOT_HOME_HERO,
            title="High hero",
            is_enabled=True,
        )
        # Enabled promo only on low — still wins that slot.
        CampaignPlacement.objects.create(
            campaign=low,
            slot=CampaignPlacement.SLOT_HOME_PROMO_LEFT,
            title="Promo",
            is_enabled=True,
        )

        res = self.client.get(f"{self.base}placements/")
        self.assertEqual(res.status_code, 200, res.data)
        placements = res.data["placements"]
        self.assertEqual(placements["HOME_HERO"]["campaign_slug"], "high-prio")
        self.assertEqual(placements["HOME_HERO"]["title"], "High hero")
        self.assertEqual(placements["HOME_PROMO_LEFT"]["campaign_slug"], "low-prio")
        self.assertIsNone(placements["HOME_PROMO_RIGHT"])
        self.assertIn("generated_at", res.data)

        filtered = self.client.get(f"{self.base}placements/", {"slots": "HOME_HERO,HOME_STRIP"})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(set(filtered.data["placements"].keys()), {"HOME_HERO", "HOME_STRIP"})
        self.assertIsNone(filtered.data["placements"]["HOME_STRIP"])

    def test_out_of_window_active_not_visible(self):
        self._create_campaign(
            slug="ended-window",
            status=Campaign.STATUS_ACTIVE,
            start_delta=-48,
            end_delta=-1,
        )
        listing = self.client.get(self.base)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data, [])
        self.assertEqual(self.client.get(f"{self.base}ended-window/").status_code, 404)
