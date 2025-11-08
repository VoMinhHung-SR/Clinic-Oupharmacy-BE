"""
Management command để kiểm tra và tạo thông báo cho thuốc sắp hết hạn
Chạy: python manage.py check_expiry_notifications
Có thể schedule bằng Celery Beat hoặc cron
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from storeApp.models import MedicineBatch, Notification


class Command(BaseCommand):
    help = 'Check medicine batches and create expiry notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--warning-days',
            type=int,
            default=30,
            help='Number of days before expiry to send warning (default: 30)',
        )
        parser.add_argument(
            '--urgent-days',
            type=int,
            default=7,
            help='Number of days before expiry to send urgent warning (default: 7)',
        )

    def handle(self, *args, **options):
        warning_days = options['warning_days']
        urgent_days = options['urgent_days']
        today = timezone.now().date()
        
        # Lấy tất cả batches chưa hết hạn và còn hàng
        batches = MedicineBatch.objects.filter(
            active=True,
            remaining_quantity__gt=0,
            expiry_date__gte=today
        ).select_related()

        created_count = 0
        urgent_count = 0
        expired_count = 0

        for batch in batches:
            days_left = batch.days_until_expiry
            batch_id = batch.id
            
            # Kiểm tra đã có notification chưa (tránh duplicate)
            existing_notification = Notification.objects.filter(
                batch_id=batch_id,
                notification_type__in=[
                    Notification.EXPIRY_WARNING,
                    Notification.EXPIRY_URGENT,
                    Notification.EXPIRED
                ],
                created_date__date=today
            ).exists()

            if existing_notification:
                continue

            # Đã hết hạn (expiry_date < today - nhưng filter đã loại bỏ, nhưng để an toàn)
            if days_left < 0:
                Notification.objects.create(
                    notification_type=Notification.EXPIRED,
                    medicine_unit_id=batch.medicine_unit_id,
                    batch_id=batch_id,
                    title=f'Thuốc đã hết hạn - Batch {batch.batch_number}',
                    message=f'Batch {batch.batch_number} đã hết hạn từ {abs(days_left)} ngày trước. Số lượng còn lại: {batch.remaining_quantity}',
                    is_read=False
                )
                expired_count += 1

            # Cảnh báo khẩn cấp (<= 7 ngày)
            elif days_left <= urgent_days:
                Notification.objects.create(
                    notification_type=Notification.EXPIRY_URGENT,
                    medicine_unit_id=batch.medicine_unit_id,
                    batch_id=batch_id,
                    title=f'Cảnh báo khẩn cấp: Thuốc sắp hết hạn - Batch {batch.batch_number}',
                    message=f'Batch {batch.batch_number} sẽ hết hạn trong {days_left} ngày. Số lượng còn lại: {batch.remaining_quantity}',
                    is_read=False
                )
                urgent_count += 1

            # Cảnh báo thông thường (<= 30 ngày)
            elif days_left <= warning_days:
                Notification.objects.create(
                    notification_type=Notification.EXPIRY_WARNING,
                    medicine_unit_id=batch.medicine_unit_id,
                    batch_id=batch_id,
                    title=f'Cảnh báo: Thuốc sắp hết hạn - Batch {batch.batch_number}',
                    message=f'Batch {batch.batch_number} sẽ hết hạn trong {days_left} ngày. Số lượng còn lại: {batch.remaining_quantity}',
                    is_read=False
                )
                created_count += 1

        # Kiểm tra các batch đã hết hạn
        expired_batches = MedicineBatch.objects.filter(
            active=True,
            remaining_quantity__gt=0,
            expiry_date__lt=today
        )

        for batch in expired_batches:
            batch_id = batch.id
            # Kiểm tra đã có notification chưa
            if not Notification.objects.filter(
                batch_id=batch_id,
                notification_type=Notification.EXPIRED,
                created_date__date=today
            ).exists():
                Notification.objects.create(
                    notification_type=Notification.EXPIRED,
                    medicine_unit_id=batch.medicine_unit_id,
                    batch_id=batch_id,
                    title=f'Thuốc đã hết hạn - Batch {batch.batch_number}',
                    message=f'Batch {batch.batch_number} đã hết hạn từ {(today - batch.expiry_date).days} ngày trước. Số lượng còn lại: {batch.remaining_quantity}',
                    is_read=False
                )
                expired_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created notifications: '
                f'{created_count} warnings, {urgent_count} urgent, {expired_count} expired'
            )
        )

