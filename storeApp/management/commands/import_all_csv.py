"""
Management command để import tất cả CSV files trong storeApp/test
Chạy: 
  - Import tất cả: python manage.py import_all_csv
  - Import một file: python manage.py import_all_csv --file storeApp/test/scraped-data-thuc-pham-chuc-nang-vitamin-1-119.csv
  - Dry-run: python manage.py import_all_csv --dry-run
"""
import csv
import json
import os
import glob
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from mainApp.models import Medicine, MedicineUnit, Category
from storeApp.models import Brand


class Command(BaseCommand):
    help = 'Import all CSV files from storeApp/test directory'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Import specific CSV file (optional)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without saving to database'
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip products that already exist (by SKU)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for bulk operations (default: 100)'
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

    def import_csv_file(self, csv_file, dry_run=False, skip_existing=False):
        """Import a single CSV file"""
        file_name = os.path.basename(csv_file)
        self.stdout.write(f'\n📄 Processing: {file_name}')
        
        # Pre-fetch brands để tránh N+1 queries
        brands = {b.name: b.id for b in Brand.objects.all()}
        
        # Category cache
        category_cache = {}
        
        imported_count = 0
        skipped_count = 0
        errors = []
        units_to_create = []
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                total_rows = sum(1 for _ in reader)
                f.seek(0)
                reader = csv.DictReader(f)  # Reset reader
                
                self.stdout.write(f'  📊 Total rows: {total_rows}')
                
                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Parse category array FIRST (cần category để check duplicate MedicineUnit)
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
                        
                        # Get SKU và name
                        sku = row.get('basicInfo.sku', '').strip()
                        name = row.get('basicInfo.name', '').strip()
                        
                        # Tìm Medicine trước (có thể reuse cho nhiều MedicineUnit với category khác)
                        medicine = None
                        if sku:
                            medicine = Medicine.objects.filter(mid=sku).first()
                        if not medicine and name:
                            medicine = Medicine.objects.filter(name=name).first()
                        
                        # Check duplicate MedicineUnit (medicine + category combination)
                        # Đây là check quan trọng: cùng Medicine nhưng khác category thì vẫn tạo mới
                        # Chỉ skip nếu MedicineUnit với (medicine + category) đã tồn tại
                        if skip_existing and medicine:
                            if MedicineUnit.objects.filter(medicine=medicine, category=category).exists():
                                skipped_count += 1
                                continue
                        
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
                        if not sku:
                            sku = None
                        
                        # Get or create Medicine (không skip Medicine, vì có thể có nhiều MedicineUnit với category khác)
                        # Medicine có thể được reuse cho nhiều MedicineUnit với category khác nhau
                        if not medicine:  # Chỉ create nếu chưa tìm thấy ở trên
                            medicine_defaults = {
                                'name': name[:254] if name else '',  # Truncate to max_length
                                'slug': row.get('basicInfo.slug', '')[:300] if row.get('basicInfo.slug') else '',
                                'web_name': row.get('basicInfo.webName', '')[:500] if row.get('basicInfo.webName') else '',
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
                                    mid=sku[:64] if sku else None,  # Truncate to max_length
                                    defaults=medicine_defaults
                                )
                            else:
                                # Fallback: use name if no SKU
                                medicine, created = Medicine.objects.get_or_create(
                                    name=name[:254] if name else '',  # Truncate to max_length
                                    defaults=medicine_defaults
                                )
                        
                        # Create MedicineUnit (duplicate check đã được làm ở trên)
                        if not dry_run:
                            # Truncate fields to max_length
                            package_size = row.get('pricing.packageSize', '')[:100] if row.get('pricing.packageSize') else ''
                            registration_number = row.get('specifications.registrationNumber', '')[:100] if row.get('specifications.registrationNumber') else ''
                            origin = row.get('specifications.origin', '')[:100] if row.get('specifications.origin') else ''
                            manufacturer = row.get('specifications.manufacturer', '')[:200] if row.get('specifications.manufacturer') else ''
                            shelf_life = row.get('specifications.shelfLife', '')[:50] if row.get('specifications.shelfLife') else ''
                            
                            unit = MedicineUnit(
                                medicine=medicine,
                                category=category,
                                price_display=price_display[:50] if price_display else '',
                                price_value=price_value,
                                package_size=package_size,
                                prices=prices,
                                price_obj=price_obj if price_obj else {},
                                image=row.get('media.image', ''),
                                images=images,
                                link=row.get('metadata.link', '')[:500] if row.get('metadata.link') else '',
                                product_ranking=int(row.get('metadata.productRanking', 0)) if row.get('metadata.productRanking') else 0,
                                display_code=int(row.get('metadata.displayCode', 0)) if row.get('metadata.displayCode') else None,
                                is_published=row.get('metadata.isPublish', 'true').lower() == 'true',
                                registration_number=registration_number,
                                origin=origin,
                                manufacturer=manufacturer,
                                shelf_life=shelf_life,
                                specifications=specifications if specifications else {},
                                in_stock=100,  # Default stock
                            )
                            units_to_create.append(unit)
                            
                            # Bulk create in batches
                            if len(units_to_create) >= self.batch_size:
                                try:
                                    MedicineUnit.objects.bulk_create(units_to_create, ignore_conflicts=True)
                                    imported_count += len(units_to_create)
                                    self.stdout.write(f'  ✓ Imported batch: {len(units_to_create)} products')
                                except Exception as e:
                                    # If bulk create fails, try individual creates
                                    self.stdout.write(self.style.WARNING(f'  ⚠ Bulk create failed, trying individual: {str(e)[:100]}'))
                                    for unit in units_to_create:
                                        try:
                                            unit.save()
                                            imported_count += 1
                                        except Exception as e2:
                                            errors.append(f'Row {row_num}: {str(e2)[:100]}')
                                units_to_create = []
                        else:
                            imported_count += 1
                            
                        if (row_num - 1) % 50 == 0:
                            self.stdout.write(f'  Progress: {row_num - 1}/{total_rows} rows processed')
                            
                    except Exception as e:
                        error_msg = f'Row {row_num}: {str(e)}'
                        errors.append(error_msg)
                        if len(errors) <= 5:  # Only show first 5 errors
                            self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
            
            # Create remaining units
            if not dry_run and units_to_create:
                try:
                    MedicineUnit.objects.bulk_create(units_to_create, ignore_conflicts=True)
                    imported_count += len(units_to_create)
                    self.stdout.write(f'  ✓ Imported final batch: {len(units_to_create)} products')
                except Exception as e:
                    # If bulk create fails, try individual creates
                    self.stdout.write(self.style.WARNING(f'  ⚠ Bulk create failed, trying individual: {str(e)[:100]}'))
                    for unit in units_to_create:
                        try:
                            unit.save()
                            imported_count += 1
                        except Exception as e2:
                            errors.append(f'Final batch: {str(e2)[:100]}')
            
            return {
                'imported': imported_count,
                'skipped': skipped_count,
                'errors': errors
            }
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Error processing file: {str(e)}'))
            return {
                'imported': imported_count,
                'skipped': skipped_count,
                'errors': [f'File error: {str(e)}'] + errors
            }

    def handle(self, *args, **options):
        csv_file = options.get('file')
        dry_run = options.get('dry_run', False)
        skip_existing = options.get('skip_existing', False)
        self.batch_size = options.get('batch_size', 100)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No data will be saved'))
        
        if skip_existing:
            self.stdout.write(self.style.WARNING('⏭️  SKIP EXISTING MODE - Will skip products with existing SKU/name or duplicate MedicineUnit'))
        
        # Get CSV files
        test_dir = os.path.join('storeApp', 'test')
        csv_files = []
        
        if csv_file:
            # Import specific file
            if os.path.exists(csv_file):
                csv_files = [csv_file]
            else:
                self.stdout.write(self.style.ERROR(f'❌ File not found: {csv_file}'))
                return
        else:
            # Import all CSV files (except test-small-batch.csv)
            pattern = os.path.join(test_dir, 'scraped-data-*.csv')
            csv_files = sorted(glob.glob(pattern))
            
            if not csv_files:
                self.stdout.write(self.style.ERROR(f'❌ No CSV files found in {test_dir}'))
                return
        
        self.stdout.write(self.style.SUCCESS(f'\n🚀 Starting import of {len(csv_files)} file(s)...'))
        
        total_stats = {
            'imported': 0,
            'skipped': 0,
            'errors': []
        }
        
        # Process each file
        for idx, csv_file in enumerate(csv_files, 1):
            self.stdout.write(f'\n[{idx}/{len(csv_files)}] Processing file...')
            
            with transaction.atomic():
                stats = self.import_csv_file(csv_file, dry_run, skip_existing)
                total_stats['imported'] += stats['imported']
                total_stats['skipped'] += stats['skipped']
                total_stats['errors'].extend(stats['errors'])
                
                if dry_run:
                    transaction.set_rollback(True)
        
        # Final summary
        self.stdout.write(self.style.SUCCESS(f'\n✅ Import completed!'))
        self.stdout.write(f'  📦 Total imported: {total_stats["imported"]} products')
        if total_stats['skipped'] > 0:
            self.stdout.write(f'  ⏭️  Total skipped: {total_stats["skipped"]} products')
        if total_stats['errors']:
            self.stdout.write(self.style.ERROR(f'  ❌ Total errors: {len(total_stats["errors"])}'))
            self.stdout.write(self.style.WARNING('  Showing first 10 errors:'))
            for error in total_stats['errors'][:10]:
                self.stdout.write(self.style.ERROR(f'    • {error}'))
            if len(total_stats['errors']) > 10:
                self.stdout.write(self.style.ERROR(f'    ... and {len(total_stats["errors"]) - 10} more errors'))
        
        # Show final counts
        if not dry_run:
            self.stdout.write(f'\n📊 Database status:')
            self.stdout.write(f'  - Medicines: {Medicine.objects.count()}')
            self.stdout.write(f'  - MedicineUnits: {MedicineUnit.objects.count()}')
            self.stdout.write(f'  - Categories: {Category.objects.count()}')

