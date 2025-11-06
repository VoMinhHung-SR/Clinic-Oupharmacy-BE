"""
Management command để tạo dữ liệu demo cho storeApp
Chạy: python manage.py create_demo_data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from storeApp.models import Brand, ShippingMethod, PaymentMethod, MedicineBatch, Notification


class Command(BaseCommand):
    help = 'Create demo data for storeApp (Brands, ShippingMethods, PaymentMethods, MedicineBatches)'

    def handle(self, *args, **options):

        # Tạo Brands
        self.stdout.write(self.style.SUCCESS('Creating Brands...'))
        brands_data = [
            {'name': 'Traphaco', 'active': True},
            {'name': 'Hậu Giang', 'active': True},
            {'name': 'Imexpharm', 'active': True},
            {'name': 'Domesco', 'active': True},
            {'name': 'Pharmedic', 'active': True},
            {'name': 'Opc', 'active': True},
            {'name': 'Sanofi', 'active': True},
            {'name': 'Abbott', 'active': True},
            {'name': 'Pfizer', 'active': True},
        ]
        
        brands = []
        for data in brands_data:
            brand, created = Brand.objects.get_or_create(
                name=data['name'],
                defaults={'active': data['active']}
            )
            brands.append(brand)
            if created:
                self.stdout.write(f'  Created brand: {brand.name}')

        # Tạo ShippingMethods
        self.stdout.write(self.style.SUCCESS('Creating Shipping Methods...'))
        shipping_methods_data = [
            {'name': 'Giao nhanh (2-4h)', 'price': 25000, 'estimated_days': 1, 'active': True},
            {'name': 'Giao tiêu chuẩn (1-2 ngày)', 'price': 15000, 'estimated_days': 2, 'active': True},
            {'name': 'Giao tiết kiệm (3-5 ngày)', 'price': 10000, 'estimated_days': 5, 'active': True},
            {'name': 'Giao trong giờ hành chính', 'price': 20000, 'estimated_days': 1, 'active': True},
        ]

        shipping_methods = []
        for data in shipping_methods_data:
            method, created = ShippingMethod.objects.get_or_create(
                name=data['name'],
                defaults={
                    'price': data['price'],
                    'estimated_days': data['estimated_days'],
                    'active': data['active']
                }
            )
            shipping_methods.append(method)
            if created:
                self.stdout.write(f'  Created shipping method: {method.name} - {method.price:,.0f}₫')

        # Tạo PaymentMethods
        self.stdout.write(self.style.SUCCESS('Creating Payment Methods...'))
        payment_methods_data = [
            {'name': 'Thanh toán khi nhận hàng (COD)', 'code': 'COD', 'active': True},
            {'name': 'Ví điện tử MoMo', 'code': 'MOMO', 'active': True},
            {'name': 'VNPay', 'code': 'VNPAY', 'active': True},
            {'name': 'ZaloPay', 'code': 'ZALOPAY', 'active': True},
            {'name': 'Chuyển khoản ngân hàng', 'code': 'BANK_TRANSFER', 'active': True},
        ]

        payment_methods = []
        for data in payment_methods_data:
            method, created = PaymentMethod.objects.get_or_create(
                code=data['code'],
                defaults={
                    'name': data['name'],
                    'active': data['active']
                }
            )
            payment_methods.append(method)
            if created:
                self.stdout.write(f'  Created payment method: {method.name} ({method.code})')

        # Tạo MedicineBatches (giả sử có MedicineUnit với id từ 1-10)
        self.stdout.write(self.style.SUCCESS('Creating Medicine Batches...'))
        today = date.today()
        
        # Tạo các batches với thời hạn khác nhau để demo notification
        batches_data = [
            {
                'batch_number': 'BATCH20250101001',
                'medicine_unit_id': 1,
                'import_date': today - timedelta(days=30),
                'expiry_date': today + timedelta(days=5),  # Sắp hết hạn (khẩn cấp)
                'quantity': 100,
                'remaining_quantity': 50,
                'import_price': 50000,
            },
            {
                'batch_number': 'BATCH20250101002',
                'medicine_unit_id': 2,
                'import_date': today - timedelta(days=60),
                'expiry_date': today + timedelta(days=15),  # Cảnh báo
                'quantity': 200,
                'remaining_quantity': 150,
                'import_price': 75000,
            },
            {
                'batch_number': 'BATCH20250101003',
                'medicine_unit_id': 3,
                'import_date': today - timedelta(days=10),
                'expiry_date': today + timedelta(days=60),  # Bình thường
                'quantity': 300,
                'remaining_quantity': 280,
                'import_price': 60000,
            },
            {
                'batch_number': 'BATCH20250101004',
                'medicine_unit_id': 4,
                'import_date': today - timedelta(days=90),
                'expiry_date': today - timedelta(days=5),  # Đã hết hạn
                'quantity': 150,
                'remaining_quantity': 30,
                'import_price': 55000,
            },
            {
                'batch_number': 'BATCH20250102001',
                'medicine_unit_id': 5,
                'import_date': today - timedelta(days=20),
                'expiry_date': today + timedelta(days=90),  # Bình thường
                'quantity': 250,
                'remaining_quantity': 200,
                'import_price': 80000,
            },
            {
                'batch_number': 'BATCH20250103001',
                'medicine_unit_id': 1,  # Cùng medicine_unit_id với batch đầu
                'import_date': today - timedelta(days=5),
                'expiry_date': today + timedelta(days=120),  # Mới nhập
                'quantity': 180,
                'remaining_quantity': 180,
                'import_price': 52000,
            },
        ]

        batches_created = 0
        for data in batches_data:
            batch, created = MedicineBatch.objects.get_or_create(
                batch_number=data['batch_number'],
                defaults=data
            )
            if created:
                batches_created += 1
                self.stdout.write(f'  Created batch: {batch.batch_number} - Exp: {batch.expiry_date}')

        # Tạo một vài Notifications mẫu
        self.stdout.write(self.style.SUCCESS('Creating Sample Notifications...'))
        notifications_data = [
            {
                'notification_type': Notification.EXPIRY_URGENT,
                'medicine_unit_id': 1,
                'batch_id': MedicineBatch.objects.filter(batch_number='BATCH20250101001').first().id if MedicineBatch.objects.filter(batch_number='BATCH20250101001').exists() else None,
                'title': 'Cảnh báo khẩn cấp: Thuốc sắp hết hạn - Batch BATCH20250101001',
                'message': 'Batch BATCH20250101001 sẽ hết hạn trong 5 ngày. Số lượng còn lại: 50',
                'is_read': False,
            },
            {
                'notification_type': Notification.EXPIRY_WARNING,
                'medicine_unit_id': 2,
                'batch_id': MedicineBatch.objects.filter(batch_number='BATCH20250101002').first().id if MedicineBatch.objects.filter(batch_number='BATCH20250101002').exists() else None,
                'title': 'Cảnh báo: Thuốc sắp hết hạn - Batch BATCH20250101002',
                'message': 'Batch BATCH20250101002 sẽ hết hạn trong 15 ngày. Số lượng còn lại: 150',
                'is_read': False,
            },
            {
                'notification_type': Notification.EXPIRED,
                'medicine_unit_id': 4,
                'batch_id': MedicineBatch.objects.filter(batch_number='BATCH20250101004').first().id if MedicineBatch.objects.filter(batch_number='BATCH20250101004').exists() else None,
                'title': 'Thuốc đã hết hạn - Batch BATCH20250101004',
                'message': 'Batch BATCH20250101004 đã hết hạn từ 5 ngày trước. Số lượng còn lại: 30',
                'is_read': False,
            },
        ]

        notifications_created = 0
        for data in notifications_data:
            if data['batch_id']:  # Chỉ tạo notification nếu batch tồn tại
                notification, created = Notification.objects.get_or_create(
                    title=data['title'],
                    defaults=data
                )
                if created:
                    notifications_created += 1

        self.stdout.write(self.style.SUCCESS(f'\n✅ Demo data created successfully!'))
        self.stdout.write(f'  - Brands: {Brand.objects.count()} total')
        self.stdout.write(f'  - Shipping Methods: {ShippingMethod.objects.count()} total')
        self.stdout.write(f'  - Payment Methods: {PaymentMethod.objects.count()} total')
        self.stdout.write(f'  - Medicine Batches: {MedicineBatch.objects.count()} total (created {batches_created} new)')
        self.stdout.write(f'  - Notifications: {Notification.objects.count()} total')

