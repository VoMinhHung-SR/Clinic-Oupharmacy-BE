"""
Management command: import số lượng lớn MedicineBatch (1 dòng ứng với mỗi unit).
Rule:
- Trừ những unit vẫn còn batch chưa hết hạn (expiry_date >= today) — không tạo batch mới cho unit đó.
- import_date: random, < ngày hiện tại, cùng năm với hiện tại.
- expiry_date: 6 | 12 | 18 | 24 tháng kể từ import_date (chọn ngẫu nhiên).
- quantity: random 100 -> 300; remaining_quantity = quantity.

Chạy local:
  python manage.py import_medicine_batches [--dry-run] [--limit N]

Chạy trong container (DB trong Docker):
  docker compose exec backend python manage.py import_medicine_batches [--dry-run] [--limit N]
"""
import random
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from mainApp.models import MedicineUnit
from storeApp.models import MedicineBatch


def add_months(d, months):
    """Cộng d thêm months tháng (tránh overflow ngày)."""
    return d + relativedelta(months=months)


def random_date_in_same_year_before_today(today):
    """Random một ngày trong cùng năm với today và trước today (bao gồm đầu năm đến hôm qua)."""
    start = date(today.year, 1, 1)
    if today <= start:
        return start
    delta = (today - start).days
    offset = random.randint(0, delta - 1) if delta > 1 else 0
    return start + timedelta(days=offset)


class Command(BaseCommand):
    help = (
        'Import MedicineBatch: 1 batch/unit (trừ unit đã còn batch chưa hết hạn). '
        'import_date random cùng năm & < hiện tại; expiry = +6/12/18/24 tháng; quantity 100-300.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ in sẽ tạo bao nhiêu batch, không ghi DB.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Giới hạn số unit xử lý (mặc định: tất cả unit đủ điều kiện).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options.get('limit')
        today = timezone.now().date()

        # Lấy tất cả MedicineUnit (active, từ default DB)
        unit_ids = list(
            MedicineUnit.objects.using('default')
            .filter(active=True)
            .values_list('id', flat=True)
        )
        if not unit_ids:
            self.stdout.write(self.style.WARNING('Không có MedicineUnit nào (active).'))
            return

        # Unit nào đã có ít nhất 1 batch chưa hết hạn (expiry_date >= today) thì bỏ qua
        units_with_valid_batch = set(
            MedicineBatch.objects.filter(
                medicine_unit_id__in=unit_ids,
                active=True,
                expiry_date__gte=today,
            ).values_list('medicine_unit_id', flat=True).distinct()
        )
        units_to_import = [uid for uid in unit_ids if uid not in units_with_valid_batch]

        if limit is not None:
            units_to_import = units_to_import[:limit]

        if not units_to_import:
            self.stdout.write(
                self.style.WARNING(
                    f'Tất cả {len(unit_ids)} unit đều đã có batch chưa hết hạn, không tạo thêm.'
                )
            )
            return

        # Chọn ngẫu nhiên: expiry = import_date + 6 | 12 | 18 | 24 tháng
        expiry_months_options = [6, 12, 18, 24]

        batches_to_create = []
        used_batch_numbers = set(
            MedicineBatch.objects.values_list('batch_number', flat=True)
        )

        for unit_id in units_to_import:
            import_date = random_date_in_same_year_before_today(today)
            months = random.choice(expiry_months_options)
            expiry_date = add_months(import_date, months)
            quantity = random.randint(100, 300)

            # batch_number unique: BATCH + YYYYMMDD + unit_id + random 3 chữ số
            for _ in range(50):
                suffix = random.randint(100, 999)
                batch_number = f"BATCH{import_date.strftime('%Y%m%d')}{unit_id}{suffix}"
                if batch_number not in used_batch_numbers:
                    used_batch_numbers.add(batch_number)
                    break
            else:
                batch_number = f"BATCH{import_date.strftime('%Y%m%d')}{unit_id}{timezone.now().strftime('%H%M%S')}"

            batches_to_create.append(
                MedicineBatch(
                    batch_number=batch_number,
                    medicine_unit_id=unit_id,
                    import_date=import_date,
                    expiry_date=expiry_date,
                    quantity=quantity,
                    remaining_quantity=quantity,
                    import_price=None,
                    active=True,
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[DRY-RUN] Sẽ tạo {len(batches_to_create)} MedicineBatch '
                    f'(đã bỏ qua {len(units_with_valid_batch)} unit còn batch chưa hết hạn).'
                )
            )
            for b in batches_to_create[:5]:
                self.stdout.write(
                    f'  {b.batch_number} unit_id={b.medicine_unit_id} '
                    f'import={b.import_date} expiry={b.expiry_date} qty={b.quantity}'
                )
            if len(batches_to_create) > 5:
                self.stdout.write(f'  ... và {len(batches_to_create) - 5} bản ghi khác.')
            return

        try:
            with transaction.atomic(using='store'):
                MedicineBatch.objects.bulk_create(batches_to_create)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Đã tạo {len(batches_to_create)} MedicineBatch. '
                    f'(Đã bỏ qua {len(units_with_valid_batch)} unit vẫn còn batch chưa hết hạn.)'
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Lỗi: {e}'))