"""
Converge Campaign statuses by wall clock (scheduled→active, *→ended)
and revert expired catalog unit promotions (P1b).

  python manage.py run_campaign_scheduler

Cron (example every 5 minutes):

  */5 * * * * cd /path/to/Clinic-Oupharmacy-BE && \\
    ./venv/bin/python manage.py run_campaign_scheduler >> /var/log/campaign_scheduler.log 2>&1

Public list/detail/placements still filter by time window if this job is late (D-14).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from storeApp.services.campaign_service import run_campaign_scheduler


class Command(BaseCommand):
    help = "Activate due scheduled campaigns and end expired scheduled/active/paused campaigns"

    def add_arguments(self, parser):
        parser.add_argument(
            "--now",
            type=str,
            default=None,
            help="Optional ISO-8601 timestamp override for tests/ops (default: timezone.now())",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        raw = options.get("now")
        if raw:
            parsed = parse_datetime(raw)
            if parsed is None:
                self.stderr.write(self.style.ERROR(f"Invalid --now value: {raw}"))
                return
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            now = parsed

        stats = run_campaign_scheduler(now=now)
        self.stdout.write(
            self.style.SUCCESS(
                "campaign scheduler ok "
                f"activated={stats['activated']} ended={stats['ended']} "
                f"scanned_activate={stats['scanned_activate']} scanned_end={stats['scanned_end']} "
                f"promo_reverted={stats.get('promo_reverted', 0)} "
                f"now={now.isoformat()}"
            )
        )
