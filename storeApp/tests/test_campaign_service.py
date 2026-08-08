"""CampaignService lifecycle unit tests (P1-T2)."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from storeApp.models import Campaign
from storeApp.services.campaign_service import (
    CampaignServiceError,
    CampaignTransitionError,
    CampaignVersionConflictError,
    apply_time_expiry,
    archive_campaign,
    end_campaign,
    pause_campaign,
    publish_campaign,
    resume_campaign,
    schedule_campaign,
)


def _future_window(*, hours_start=1, hours_end=48):
    now = timezone.now()
    return now + timedelta(hours=hours_start), now + timedelta(hours=hours_end)


class CampaignServiceLifecycleTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        cache.clear()

    def _draft(self, **kwargs):
        start_at, end_at = _future_window()
        defaults = {
            "name": "Ops",
            "slug": kwargs.pop("slug", "camp-lifecycle"),
            "title": "Title",
            "status": Campaign.STATUS_DRAFT,
            "start_at": start_at,
            "end_at": end_at,
        }
        defaults.update(kwargs)
        return Campaign.objects.create(**defaults)

    def test_schedule_and_publish_now_sets_start_at(self):
        campaign = self._draft(slug="pub-now", start_at=timezone.now() + timedelta(days=2))
        original_start = campaign.start_at
        scheduled = schedule_campaign(campaign_id=campaign.id, expected_version=campaign.version)
        self.assertEqual(scheduled.status, Campaign.STATUS_SCHEDULED)
        self.assertEqual(scheduled.version, 2)

        published = publish_campaign(campaign_id=scheduled.id, expected_version=scheduled.version)
        self.assertEqual(published.status, Campaign.STATUS_ACTIVE)
        self.assertLessEqual(published.start_at, timezone.now() + timedelta(seconds=2))
        self.assertLess(published.start_at, original_start)
        self.assertEqual(published.version, 3)

    def test_publish_from_draft_requires_future_end_at(self):
        now = timezone.now()
        campaign = self._draft(
            slug="bad-end",
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(minutes=1),
        )
        with self.assertRaises(CampaignServiceError):
            publish_campaign(campaign_id=campaign.id, expected_version=campaign.version)

    def test_illegal_transition_active_to_draft(self):
        campaign = self._draft(slug="illegal")
        published = publish_campaign(campaign_id=campaign.id, expected_version=campaign.version)
        with self.assertRaises(CampaignTransitionError):
            archive_campaign(campaign_id=published.id, expected_version=published.version)

    def test_pause_resume_and_resume_after_end_forces_ended(self):
        campaign = self._draft(slug="pause-resume")
        published = publish_campaign(campaign_id=campaign.id, expected_version=campaign.version)
        paused = pause_campaign(campaign_id=published.id, expected_version=published.version)
        self.assertEqual(paused.status, Campaign.STATUS_PAUSED)

        resumed = resume_campaign(campaign_id=paused.id, expected_version=paused.version)
        self.assertEqual(resumed.status, Campaign.STATUS_ACTIVE)

        paused2 = pause_campaign(campaign_id=resumed.id, expected_version=resumed.version)
        now = timezone.now()
        # Keep CHECK end_at > start_at while placing window in the past.
        Campaign.objects.filter(id=paused2.id).update(
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(minutes=1),
        )
        paused2.refresh_from_db()
        forced = resume_campaign(campaign_id=paused2.id, expected_version=paused2.version)
        self.assertEqual(forced.status, Campaign.STATUS_ENDED)

    def test_version_conflict(self):
        campaign = self._draft(slug="ver-conflict")
        with self.assertRaises(CampaignVersionConflictError):
            schedule_campaign(campaign_id=campaign.id, expected_version=campaign.version + 99)

    def test_end_then_archive(self):
        campaign = self._draft(slug="end-arch")
        published = publish_campaign(campaign_id=campaign.id, expected_version=campaign.version)
        ended = end_campaign(campaign_id=published.id, expected_version=published.version)
        self.assertEqual(ended.status, Campaign.STATUS_ENDED)
        archived = archive_campaign(campaign_id=ended.id, expected_version=ended.version)
        self.assertEqual(archived.status, Campaign.STATUS_ARCHIVED)

    def test_apply_time_expiry(self):
        campaign = self._draft(slug="expiry")
        published = publish_campaign(campaign_id=campaign.id, expected_version=campaign.version)
        now = timezone.now()
        Campaign.objects.filter(id=published.id).update(
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(seconds=1),
        )
        expired = apply_time_expiry(campaign_id=published.id, now=now)
        self.assertEqual(expired.status, Campaign.STATUS_ENDED)
        self.assertEqual(expired.version, published.version + 1)
