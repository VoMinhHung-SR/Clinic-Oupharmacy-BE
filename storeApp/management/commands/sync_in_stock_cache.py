"""
Management command: đồng bộ MedicineUnit.in_stock từ tổng remaining_quantity của Batches (store).
Duyệt tất cả medicine_unit_id có trong MedicineBatch (store), gọi sync_in_stock_cache(unit_id).
Có thể chạy sau khi sửa DB tay hoặc để đảm bảo cache khớp với Batches.

  python manage.py sync_in_stock_cache
  docker compose exec backend python manage.py sync_in_stock_cache
"""
from django.core.management.base import BaseCommand

from storeApp.models import MedicineBatch
from storeApp.services.stock import sync_in_stock_cache


class Command(BaseCommand):
    help = 'Sync MedicineUnit.in_stock from Batches (store DB) for all units that have batches.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--unit',
            type=int,
            default=None,
            help='Sync only this medicine_unit_id (default: all units with batches).',
        )

    def handle(self, *args, **options):
        unit_id = options.get('unit')
        if unit_id is not None:
            sync_in_stock_cache(unit_id)
            self.stdout.write(self.style.SUCCESS(f'Synced in_stock cache for medicine_unit_id={unit_id}'))
            return

        unit_ids = list(
            MedicineBatch.objects.using('store')
            .values_list('medicine_unit_id', flat=True)
            .distinct()
        )
        if not unit_ids:
            self.stdout.write(self.style.WARNING('No medicine_unit_id found in MedicineBatch (store).'))
            return

        for uid in unit_ids:
            sync_in_stock_cache(uid)
        self.stdout.write(
            self.style.SUCCESS(f'Synced in_stock cache for {len(unit_ids)} medicine unit(s).')
        )
