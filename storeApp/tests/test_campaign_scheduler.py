"""Idempotent campaign scheduler tests (P2-T2). Uses explicit `now=` (freezegun equivalent)."""

from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from io import StringIO

from storeApp.models import Campaign
from storeApp.services.campaign_public import public_visible_queryset
from storeApp.services.campaign_service import run_campaign_scheduler


class CampaignSchedulerTests(TestCase):
    databases = {"default", "store"}

    def _campaign(self, *, slug, status, start_at, end_at, priority=0):
        return Campaign.objects.create(
            name=slug,
            slug=slug,
            title=slug,
            status=status,
            priority=priority,
            start_at=start_at,
            end_at=end_at,
        )

    def test_activate_scheduled_then_idempotent(self):
        now = timezone.now()
        camp = self._campaign(
            slug="sched-activate",
            status=Campaign.STATUS_SCHEDULED,
            start_at=now - timedelta(minutes=5),
            end_at=now + timedelta(hours=2),
        )
        first = run_campaign_scheduler(now=now)
        camp.refresh_from_db()
        self.assertEqual(camp.status, Campaign.STATUS_ACTIVE)
        self.assertEqual(first["activated"], 1)
        self.assertEqual(first["ended"], 0)

        second = run_campaign_scheduler(now=now)
        camp.refresh_from_db()
        self.assertEqual(camp.status, Campaign.STATUS_ACTIVE)
        self.assertEqual(second["activated"], 0)
        self.assertEqual(second["ended"], 0)

    def test_end_active_and_scheduled_past_end(self):
        now = timezone.now()
        active = self._campaign(
            slug="active-end",
            status=Campaign.STATUS_ACTIVE,
            start_at=now - timedelta(hours=3),
            end_at=now - timedelta(minutes=1),
        )
        scheduled = self._campaign(
            slug="sched-end",
            status=Campaign.STATUS_SCHEDULED,
            start_at=now - timedelta(hours=3),
            end_at=now - timedelta(minutes=1),
        )
        stats = run_campaign_scheduler(now=now)
        active.refresh_from_db()
        scheduled.refresh_from_db()
        self.assertEqual(active.status, Campaign.STATUS_ENDED)
        self.assertEqual(scheduled.status, Campaign.STATUS_ENDED)
        self.assertEqual(stats["ended"], 2)
        self.assertEqual(stats["activated"], 0)

        again = run_campaign_scheduler(now=now)
        self.assertEqual(again["ended"], 0)

    def test_public_filter_ok_if_status_lags(self):
        """D-14: stale active past end_at must not appear publicly even before cron."""
        now = timezone.now()
        stale = self._campaign(
            slug="stale-active",
            status=Campaign.STATUS_ACTIVE,
            start_at=now - timedelta(hours=5),
            end_at=now - timedelta(minutes=1),
        )
        self.assertFalse(public_visible_queryset(now=now).filter(id=stale.id).exists())
        # Cron later still converges status.
        run_campaign_scheduler(now=now)
        stale.refresh_from_db()
        self.assertEqual(stale.status, Campaign.STATUS_ENDED)

    def test_management_command_smoke(self):
        now = timezone.now()
        self._campaign(
            slug="cmd-activate",
            status=Campaign.STATUS_SCHEDULED,
            start_at=now - timedelta(minutes=1),
            end_at=now + timedelta(hours=1),
        )
        out = StringIO()
        call_command("run_campaign_scheduler", now=now.isoformat(), stdout=out)
        self.assertIn("activated=1", out.getvalue())
        self.assertEqual(Campaign.objects.get(slug="cmd-activate").status, Campaign.STATUS_ACTIVE)
