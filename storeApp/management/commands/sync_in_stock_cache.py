"""
Management command: đồng bộ ProductVariant.in_stock từ tổng remaining_quantity của MedicineBatch (store).

Duyệt tất cả product_variant_id có trong MedicineBatch (store), gọi sync_in_stock_cache(variant_id).
Có thể chạy sau khi sửa DB tay hoặc để đảm bảo cache khớp với Batches.

  python manage.py sync_in_stock_cache
  docker compose exec backend python manage.py sync_in_stock_cache
"""
from django.core.management.base import BaseCommand

from storeApp.models import MedicineBatch
from storeApp.services.stock import sync_in_stock_cache


class Command(BaseCommand):
    help = 'Sync ProductVariant.in_stock from Batches (store DB) for all variants that have batches.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--variant',
            type=int,
            default=None,
            help='Sync only this product_variant id (default: all variants with batches).',
        )
        parser.add_argument(
            '--unit',
            type=int,
            default=None,
            help='Deprecated alias for --variant (same as product_variant id).',
        )

    def handle(self, *args, **options):
        variant_id = options.get('variant')
        if variant_id is None and options.get('unit') is not None:
            variant_id = options['unit']

        if variant_id is not None:
            sync_in_stock_cache(variant_id)
            self.stdout.write(
                self.style.SUCCESS(f'Synced in_stock cache for product_variant_id={variant_id}')
            )
            return

        variant_ids = list(
            MedicineBatch.objects.using('store')
            .exclude(product_variant_id__isnull=True)
            .values_list('product_variant_id', flat=True)
            .distinct()
        )
        if not variant_ids:
            self.stdout.write(
                self.style.WARNING('No product_variant_id found in MedicineBatch (store).')
            )
            return

        for vid in variant_ids:
            sync_in_stock_cache(vid)
        self.stdout.write(
            self.style.SUCCESS(f'Synced in_stock cache for {len(variant_ids)} product variant(s).')
        )
