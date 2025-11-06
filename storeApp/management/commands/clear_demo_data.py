"""
Management command để xóa dữ liệu demo trong storeApp
Chạy: python manage.py clear_demo_data
"""
from django.core.management.base import BaseCommand
from storeApp.models import Brand, ShippingMethod, PaymentMethod, Order, OrderItem, MedicineBatch, Notification


class Command(BaseCommand):
    help = 'Clear all demo data from storeApp'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        # Đếm số lượng records trước khi xóa
        brands_count = Brand.objects.count()
        shipping_count = ShippingMethod.objects.count()
        payment_count = PaymentMethod.objects.count()
        orders_count = Order.objects.count()
        order_items_count = OrderItem.objects.count()
        batches_count = MedicineBatch.objects.count()
        notifications_count = Notification.objects.count()

        total = brands_count + shipping_count + payment_count + orders_count + order_items_count + batches_count + notifications_count

        if total == 0:
            self.stdout.write(self.style.WARNING('No data to clear. All tables are empty.'))
            return

        # Hiển thị thống kê
        self.stdout.write(self.style.WARNING('\n⚠️  Will delete the following data:'))
        self.stdout.write(f'  - Brands: {brands_count}')
        self.stdout.write(f'  - Shipping Methods: {shipping_count}')
        self.stdout.write(f'  - Payment Methods: {payment_count}')
        self.stdout.write(f'  - Orders: {orders_count}')
        self.stdout.write(f'  - Order Items: {order_items_count}')
        self.stdout.write(f'  - Medicine Batches: {batches_count}')
        self.stdout.write(f'  - Notifications: {notifications_count}')
        self.stdout.write(f'  - TOTAL: {total} records\n')

        # Xác nhận
        if not options['confirm']:
            confirm = input('Are you sure you want to delete all this data? (yes/no): ')
            if confirm.lower() not in ['yes', 'y']:
                self.stdout.write(self.style.ERROR('Operation cancelled.'))
                return

        # Xóa dữ liệu (theo thứ tự để tránh lỗi foreign key)
        self.stdout.write(self.style.WARNING('Deleting data...'))

        # Xóa OrderItems trước (do có FK đến Order)
        if order_items_count > 0:
            OrderItem.objects.all().delete()
            self.stdout.write(f'  ✓ Deleted {order_items_count} Order Items')

        # Xóa Orders
        if orders_count > 0:
            Order.objects.all().delete()
            self.stdout.write(f'  ✓ Deleted {orders_count} Orders')

        # Xóa Notifications
        if notifications_count > 0:
            Notification.objects.all().delete()
            self.stdout.write(f'  ✓ Deleted {notifications_count} Notifications')

        # Xóa MedicineBatches
        if batches_count > 0:
            MedicineBatch.objects.all().delete()
            self.stdout.write(f'  ✓ Deleted {batches_count} Medicine Batches')

        # Xóa ShippingMethods
        if shipping_count > 0:
            ShippingMethod.objects.all().delete()
            self.stdout.write(f'  ✓ Deleted {shipping_count} Shipping Methods')

        # Xóa PaymentMethods
        if payment_count > 0:
            PaymentMethod.objects.all().delete()
            self.stdout.write(f'  ✓ Deleted {payment_count} Payment Methods')

        # Xóa Brands
        if brands_count > 0:
            Brand.objects.all().delete()
            self.stdout.write(f'  ✓ Deleted {brands_count} Brands')

        self.stdout.write(self.style.SUCCESS('\n✅ All demo data cleared successfully!'))

