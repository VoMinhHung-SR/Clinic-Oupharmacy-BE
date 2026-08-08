"""Public campaign cache + transition observability (P6-T2)."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import Campaign, CampaignPlacement
from storeApp.services.campaign_cache import (
    cache_version,
    invalidate_public_campaign_cache,
    public_slug_404_count,
)
from storeApp.services.campaign_service import publish_campaign, schedule_campaign


class CampaignPublicCacheTests(APITestCase):
    databases = {"default", "store"}
    base = "/api/store/campaigns/"

    def setUp(self):
        cache.clear()
        now = timezone.now()
        self.high = Campaign.objects.create(
            name="High",
            slug="cache-high",
            title="High",
            status=Campaign.STATUS_ACTIVE,
            priority=100,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=2),
        )
        self.low = Campaign.objects.create(
            name="Low",
            slug="cache-low",
            title="Low",
            status=Campaign.STATUS_ACTIVE,
            priority=1,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=2),
        )
        CampaignPlacement.objects.create(
            campaign=self.high,
            slot=CampaignPlacement.SLOT_HOME_HERO,
            title="High hero",
            is_enabled=True,
        )
        CampaignPlacement.objects.create(
            campaign=self.low,
            slot=CampaignPlacement.SLOT_HOME_HERO,
            title="Low hero",
            is_enabled=True,
        )

    def test_placements_cache_stale_until_invalidate(self):
        first = self.client.get(f"{self.base}placements/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["placements"]["HOME_HERO"]["campaign_slug"], "cache-high")

        Campaign.objects.filter(id=self.high.id).update(priority=0)
        stale = self.client.get(f"{self.base}placements/")
        self.assertEqual(stale.data["placements"]["HOME_HERO"]["campaign_slug"], "cache-high")

        invalidate_public_campaign_cache()
        fresh = self.client.get(f"{self.base}placements/")
        self.assertEqual(fresh.data["placements"]["HOME_HERO"]["campaign_slug"], "cache-low")

    def test_publish_invalidates_public_list(self):
        now = timezone.now()
        draft = Campaign.objects.create(
            name="Soon",
            slug="cache-soon",
            title="Soon",
            status=Campaign.STATUS_DRAFT,
            priority=50,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
        )
        listing = self.client.get(self.base)
        slugs = {row["slug"] for row in listing.data}
        self.assertNotIn("cache-soon", slugs)

        publish_campaign(campaign_id=draft.id, expected_version=draft.version)
        listing2 = self.client.get(self.base)
        slugs2 = {row["slug"] for row in listing2.data}
        self.assertIn("cache-soon", slugs2)

    def test_public_404_increments_counter(self):
        before = public_slug_404_count("missing-camp")
        res = self.client.get(f"{self.base}missing-camp/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(public_slug_404_count("missing-camp"), before + 1)


class CampaignTransitionLogTests(TestCase):
    databases = {"default", "store"}

    def test_schedule_logs_transition(self):
        now = timezone.now()
        campaign = Campaign.objects.create(
            name="Log",
            slug="log-camp",
            title="Log",
            status=Campaign.STATUS_DRAFT,
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(days=2),
        )
        version_before = cache_version()
        with self.assertLogs("storeApp.campaign", level="INFO") as captured:
            schedule_campaign(campaign_id=campaign.id, expected_version=campaign.version, actor_user_id=99)
        joined = "\n".join(captured.output)
        self.assertIn("campaign_transition", joined)
        self.assertIn("from=draft", joined)
        self.assertIn("to=scheduled", joined)
        self.assertIn("actor=99", joined)
        self.assertGreater(cache_version(), version_before)
