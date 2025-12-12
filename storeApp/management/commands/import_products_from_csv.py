"""
Management command để import products từ CSV
Chạy: python manage.py import_products_from_csv --file storeApp/test/test-small-batch.csv
"""
import csv
import json
import re
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from mainApp.models import Medicine, MedicineUnit, Category
from storeApp.models import Brand


class Command(BaseCommand):
    help = 'Import products from CSV file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to CSV file'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without saving to database'
        )

    def parse_price_value(self, price_display):
        """Parse price_display to float value"""
        if not price_display:
            return 0
        # Remove 'đ' and dots, keep only numbers
        price_str = price_display.replace('đ', '').replace('.', '').strip()
        try:
            return float(price_str)
        except:
            return 0

    def handle(self, *args, **options):
        csv_file = options['file']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No data will be saved'))
        
        # Pre-fetch brands để tránh N+1 queries
        brands = {b.name: b.id for b in Brand.objects.all()}
        self.stdout.write(f'📦 Loaded {len(brands)} brands')
        
        # Category cache
        category_cache = {}
        
        imported_count = 0
        errors = []
        
        with transaction.atomic():
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row_num, row in enumerate(reader, start=2):  # Start from 2 (header is row 1)
                    try:
                        # Parse category array
                        category_json = row.get('category.category', '[]')
                        try:
                            category_array = json.loads(category_json) if category_json else []
                        except:
                            category_array = []
                        
                        # Get or create category
                        category = None
                        if category_array:
                            category = Category.get_or_create_from_array(
                                category_array,
                                cache=category_cache
                            )
                        
                        # Parse price value
                        price_display = row.get('pricing.priceDisplay', '').strip()
                        price_value = self.parse_price_value(price_display)
                        
                        # Parse images array
                        images_json = row.get('media.images', '[]')
                        try:
                            images = json.loads(images_json) if images_json else []
                        except:
                            images = []
                        
                        # Parse prices array
                        prices_json = row.get('pricing.prices', '[]')
                        try:
                            prices = json.loads(prices_json) if prices_json else []
                        except:
                            prices = []
                        
                        # Parse price_obj
                        price_obj_json = row.get('pricing.priceObj', '{}')
                        try:
                            price_obj = json.loads(price_obj_json) if price_obj_json else {}
                        except:
                            price_obj = {}
                        
                        # Parse specifications
                        specs_json = row.get('specifications.specifications', '{}')
                        try:
                            specifications = json.loads(specs_json) if specs_json else {}
                        except:
                            specifications = {}
                        
                        # Get brand_id
                        brand_name = row.get('basicInfo.brand', '').strip()
                        brand_id = brands.get(brand_name)
                        
                        # Get SKU/MID
                        sku = row.get('basicInfo.sku', '').strip()
                        if not sku:
                            sku = None
                        
                        # Create Medicine
                        medicine_defaults = {
                            'name': row.get('basicInfo.name', ''),
                            'slug': row.get('basicInfo.slug', ''),
                            'web_name': row.get('basicInfo.webName', ''),
                            'description': row.get('content.description', ''),
                            'ingredients': row.get('content.ingredients', ''),
                            'usage': row.get('content.usage', ''),
                            'dosage': row.get('content.dosage', ''),
                            'adverse_effect': row.get('content.adverseEffect', ''),
                            'careful': row.get('content.careful', ''),
                            'preservation': row.get('content.preservation', ''),
                            'brand_id': brand_id,
                        }
                        
                        if sku:
                            medicine, created = Medicine.objects.get_or_create(
                                mid=sku,
                                defaults=medicine_defaults
                            )
                        else:
                            # Fallback: use name if no SKU
                            medicine, created = Medicine.objects.get_or_create(
                                name=row.get('basicInfo.name', ''),
                                defaults=medicine_defaults
                            )
                        
                        # Create MedicineUnit
                        if not dry_run:
                            unit = MedicineUnit.objects.create(
                                medicine=medicine,
                                category=category,
                                price_display=price_display,
                                price_value=price_value,
                                package_size=row.get('pricing.packageSize', ''),
                                prices=prices,
                                price_obj=price_obj if price_obj else {},
                                image=row.get('media.image', ''),
                                images=images,
                                link=row.get('metadata.link', ''),
                                product_ranking=int(row.get('metadata.productRanking', 0)) if row.get('metadata.productRanking') else 0,
                                display_code=int(row.get('metadata.displayCode', 0)) if row.get('metadata.displayCode') else None,
                                is_published=row.get('metadata.isPublish', 'true').lower() == 'true',
                                registration_number=row.get('specifications.registrationNumber', ''),
                                origin=row.get('specifications.origin', ''),
                                manufacturer=row.get('specifications.manufacturer', ''),
                                shelf_life=row.get('specifications.shelfLife', ''),
                                specifications=specifications if specifications else {},
                                in_stock=100,  # Default stock
                            )
                            imported_count += 1
                            self.stdout.write(self.style.SUCCESS(f'  ✓ Row {row_num}: {medicine.name}'))
                        else:
                            imported_count += 1
                            self.stdout.write(f'  ✓ Row {row_num}: {medicine.name} (DRY RUN)')
                            
                    except Exception as e:
                        import traceback
                        error_msg = f'Row {row_num}: {str(e)}'
                        errors.append(error_msg)
                        self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
                        if dry_run:
                            self.stdout.write(traceback.format_exc())
            
            if dry_run:
                # Rollback transaction in dry-run mode
                transaction.set_rollback(True)
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f'\n✅ Import completed!'))
        self.stdout.write(f'  - Imported: {imported_count} products')
        if errors:
            self.stdout.write(self.style.ERROR(f'  - Errors: {len(errors)}'))
            for error in errors[:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(f'    • {error}'))
            if len(errors) > 10:
                self.stdout.write(self.style.ERROR(f'    ... and {len(errors) - 10} more errors'))

