from django.core.management.base import BaseCommand

from storeApp.models.cabinet import DEFAULT_ALERT_DEDUPE_DAYS
from storeApp.services.cabinet_alert_scan import scan_cabinet_expiry_alerts


class Command(BaseCommand):
    help = "Scan personal cabinets and create HSD inbox alerts (not warehouse notifications)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dedupe-days",
            type=int,
            default=DEFAULT_ALERT_DEDUPE_DAYS,
            help=f"Skip if same item+kind alert exists within N days (default {DEFAULT_ALERT_DEDUPE_DAYS}).",
        )

    def handle(self, *args, **options):
        result = scan_cabinet_expiry_alerts(dedupe_days=options["dedupe_days"])
        self.stdout.write(
            self.style.SUCCESS(
                "cabinet alerts: created={created} dedupe={skipped_dedupe} "
                "other_status={skipped_status} scanned={scanned} day={today}".format(**result)
            )
        )
