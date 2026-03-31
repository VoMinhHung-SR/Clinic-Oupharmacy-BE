"""
Cập nhật unit_price_snapshot khi đang null hoặc 0 nhưng còn product_variant_unit đã publish.
Dry-run: python manage.py backfill_prescription_unit_price_snapshots --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from mainApp.models import PrescriptionDetail
from storeApp.models import ProductVariantUnit


class Command(BaseCommand):
    help = "Backfill PrescriptionDetail.unit_price_snapshot from ProductVariantUnit price when snapshot is missing or zero."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print only, do not update DB.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        qs = PrescriptionDetail.objects.filter(active=True).exclude(
            product_variant_unit_id__isnull=True
        )
        scanned = 0
        would_update = 0
        updated = 0

        for detail in qs.iterator():
            scanned += 1
            snap = detail.unit_price_snapshot
            if snap is not None and float(snap) != 0:
                continue

            pvu = (
                ProductVariantUnit.objects.using("store")
                .filter(id=detail.product_variant_unit_id, is_published=True)
                .first()
            )
            if not pvu or pvu.price_value is None:
                continue

            new_price = pvu.price_value
            would_update += 1
            if dry:
                self.stdout.write(
                    f"[dry-run] id={detail.pk} prescribing_id={detail.prescribing_id} "
                    f"snapshot={snap!r} -> {new_price}"
                )
                continue

            with transaction.atomic():
                PrescriptionDetail.objects.filter(pk=detail.pk).update(
                    unit_price_snapshot=new_price
                )
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. scanned={scanned} eligible={would_update} "
                f"{'updated=' + str(updated) if not dry else '(dry-run)'} "
                f"dry_run={dry}"
            )
        )
