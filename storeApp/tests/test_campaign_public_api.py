"""Public campaign API tests (P2-T1)."""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import (
    Campaign,
    CampaignCategory,
    CampaignPlacement,
    CampaignProduct,
    CampaignVoucher,
    Voucher,
)


class CampaignPublicApiTests(APITestCase):
    databases = {"default", "store"}
    base = "/api/store/campaigns/"

    def setUp(self):
        cache.clear()

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

    def test_public_detail_includes_scope(self):
        active = self._create_campaign(slug="scoped-live", status=Campaign.STATUS_ACTIVE)
        CampaignProduct.objects.create(campaign=active, product_mid="MID100", sort_order=0)
        CampaignProduct.objects.create(campaign=active, product_mid="MID200", sort_order=1)
        CampaignCategory.objects.create(
            campaign=active, category_slug="duoc-my-pham", sort_order=0
        )

        res = self.client.get(f"{self.base}{active.slug}/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["product_mids"], ["MID100", "MID200"])
        self.assertEqual(res.data["category_slugs"], ["duoc-my-pham"])

    def test_public_detail_omits_non_displayable_vouchers(self):
        active = self._create_campaign(slug="voucher-live", status=Campaign.STATUS_ACTIVE)
        live = Voucher.objects.create(
            code="SHOW10",
            type="PERCENT",
            value="10.00",
            description="Show me",
            is_active=True,
        )
        dead = Voucher.objects.create(
            code="HIDE10",
            type="PERCENT",
            value="10.00",
            is_active=False,
        )
        CampaignVoucher.objects.create(campaign=active, voucher=live, sort_order=0, is_featured=True)
        CampaignVoucher.objects.create(campaign=active, voucher=dead, sort_order=1, is_featured=True)

        res = self.client.get(f"{self.base}{active.slug}/")
        self.assertEqual(res.status_code, 200, res.data)
        codes = [row["code"] for row in res.data["vouchers"]]
        self.assertEqual(codes, ["SHOW10"])
        self.assertTrue(res.data["vouchers"][0]["is_displayable"])
        self.assertEqual(res.data["vouchers"][0]["type"], "PERCENT")

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
            slot=CampaignPlacement.SLOT_HOME_SECONDARY,
            title="Promo",
            is_enabled=True,
        )

        res = self.client.get(f"{self.base}placements/")
        self.assertEqual(res.status_code, 200, res.data)
        placements = res.data["placements"]
        self.assertIsInstance(placements["HOME_HERO"], list)
        self.assertEqual(len(placements["HOME_HERO"]), 1)
        self.assertEqual(placements["HOME_HERO"][0]["campaign_slug"], "high-prio")
        self.assertEqual(placements["HOME_HERO"][0]["title"], "High hero")
        self.assertIsInstance(placements["HOME_SECONDARY"], list)
        self.assertEqual(placements["HOME_SECONDARY"][0]["campaign_slug"], "low-prio")
        self.assertIsNone(placements["HOME_NOTICE_BOTTOM"])
        self.assertNotIn("HOME_PROMO_LEFT", placements)
        self.assertIn("generated_at", res.data)

        filtered = self.client.get(
            f"{self.base}placements/", {"slots": "HOME_HERO,HOME_STRIP"}
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(
            set(filtered.data["placements"].keys()),
            {"HOME_HERO", "HOME_NOTICE_TOP"},
        )
        self.assertIsNone(filtered.data["placements"]["HOME_NOTICE_TOP"])

    def test_placements_hero_slides_same_campaign_capped(self):
        camp = self._create_campaign(slug="hero-slides", status=Campaign.STATUS_ACTIVE, priority=50)
        for i in range(4):
            CampaignPlacement.objects.create(
                campaign=camp,
                slot=CampaignPlacement.SLOT_HOME_HERO,
                title=f"Slide {i}",
                sort_order=i,
                is_enabled=True,
            )
        res = self.client.get(f"{self.base}placements/", {"slots": "HOME_HERO"})
        self.assertEqual(res.status_code, 200, res.data)
        slides = res.data["placements"]["HOME_HERO"]
        self.assertEqual(len(slides), 3)
        self.assertEqual([s["title"] for s in slides], ["Slide 0", "Slide 1", "Slide 2"])
        self.assertTrue(all(s["campaign_slug"] == "hero-slides" for s in slides))

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
