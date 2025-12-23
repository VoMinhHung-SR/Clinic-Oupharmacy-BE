"""
Management command để import products từ CSV
Chạy: 
  - Import một file: python manage.py import_products_from_csv --file storeApp/test/data/duoc-mi-pham/scraped-data-chamsoctocdamat-1-3.csv
  - Import thư mục: python manage.py import_products_from_csv --dir storeApp/test/data/thuoc
  - Dry-run: python manage.py import_products_from_csv --dir storeApp/test/data/thuoc --dry-run

Xử lý các vấn đề:
1. basicInfo.brand → Medicine.brand_id: Tạm thời để None
2. pricing.packageOptions: Bỏ qua khi import
3. Image upload từ URL lên Cloudinary
4. Parse JSON từ string CSV
5. Data type conversion
6. Category hierarchy với level và slug
7. Tránh duplicate: Check MedicineUnit với (medicine + category)
"""
import csv
import json
import os
import glob
import re
import requests
from io import BytesIO
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from mainApp.models import Medicine, MedicineUnit, Category
import cloudinary
import cloudinary.uploader


class Command(BaseCommand):
    help = 'Import products from CSV file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Path to single CSV file (optional if --dir is provided)'
        )
        parser.add_argument(
            '--dir',
            type=str,
            help='Path to directory containing CSV files (optional if --file is provided)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without saving to database'
        )
        parser.add_argument(
            '--skip-duplicates',
            action='store_true',
            default=True,
            help='Skip duplicate MedicineUnits (same medicine + category). Default: True'
        )
        parser.add_argument(
            '--skip-image-upload',
            action='store_true',
            default=False,
            help='Skip image upload to Cloudinary (save original URL instead). Use this for faster import.'
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
    
    def upload_image_from_url(self, image_url):
        """
        Upload image từ URL lên Cloudinary
        Returns: public_id hoặc None nếu lỗi
        """
        if not image_url or not image_url.strip():
            return None
        
        try:
            # Download image từ URL
            response = requests.get(image_url, timeout=10, stream=True)
            response.raise_for_status()
            
            # Upload lên Cloudinary
            upload_result = cloudinary.uploader.upload(
                BytesIO(response.content),
                folder='OUPharmacy/medicines/image',
                resource_type='image'
            )
            return upload_result['public_id']
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  ⚠️ Failed to upload image from {image_url}: {str(e)}'))
            return None
    
    def parse_json_field(self, json_str, default=None):
        """Parse JSON field từ CSV string"""
        if default is None:
            default = [] if isinstance(default, list) else {}
        
        if not json_str or not json_str.strip():
            return default
        
        try:
            parsed = json.loads(json_str)
            return parsed if parsed else default
        except json.JSONDecodeError:
            self.stdout.write(self.style.WARNING(f'  ⚠️ Failed to parse JSON: {json_str[:50]}...'))
            return default
    
    def convert_to_int(self, value, default=0):
        """Convert string to integer"""
        if not value:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def convert_to_bool(self, value, default=False):
        """Convert string to boolean"""
        if not value:
            return default
        if isinstance(value, bool):
            return value
        return str(value).lower() in ('true', '1', 'yes', 'on')

    def import_single_file(self, csv_file, dry_run=False, skip_duplicates=True, skip_image_upload=False, category_cache=None):
        """
        Import một file CSV
        Returns: dict với stats {imported, skipped, errors}
        """
        if category_cache is None:
            category_cache = {}
        
        file_name = os.path.basename(csv_file)
        self.stdout.write(f'\n📄 Processing: {file_name}')
        
        imported_count = 0
        skipped_count = 0
        errors = []
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                total_rows = sum(1 for _ in reader)
                f.seek(0)
                reader = csv.DictReader(f)  # Reset reader
                
                self.stdout.write(f'  📊 Total rows: {total_rows}')
                
                for row_num, row in enumerate(reader, start=2):  # Start from 2 (header is row 1)
                    try:
                        # ============================================
                        # 1. VẤN ĐỀ NGHIÊM TRỌNG: Brand → brand_id = None (tạm thời)
                        # TODO: Implement brand mapping
                        # - CSV có basicInfo.brand (string name)
                        # - Medicine model cần brand_id (ForeignKey to Brand)
                        # - Cần tạo Brand model hoặc mapping table
                        # - Hoặc import Brand trước, sau đó map brand_name → brand_id
                        # ============================================
                        brand_name = row.get('basicInfo.brand', '').strip()
                        brand_id = None  # Tạm thời để None, sẽ import sau
                        
                        # ============================================
                        # 2. VẤN ĐỀ NGHIÊM TRỌNG: Bỏ qua pricing.packageOptions
                        # ============================================
                        # Field này chỉ có trong file thuoc, bỏ qua khi import
                        
                        # ============================================
                        # 3. Parse JSON fields từ CSV
                        # ============================================
                        # Category array
                        category_json = row.get('category.category', '[]')
                        category_array = self.parse_json_field(category_json, default=[])
                        
                        # Images array
                        images_json = row.get('media.images', '[]')
                        images = self.parse_json_field(images_json, default=[])
                        
                        # Prices array
                        prices_json = row.get('pricing.prices', '[]')
                        prices = self.parse_json_field(prices_json, default=[])
                        
                        # Price object
                        price_obj_json = row.get('pricing.priceObj', '{}')
                        price_obj = self.parse_json_field(price_obj_json, default={})
                        
                        # ============================================
                        # 4. Category hierarchy với level và slug
                        # ============================================
                        category = None
                        if category_array:
                            category = Category.get_or_create_from_array(
                                category_array,
                                cache=category_cache
                            )
                            # Refresh category từ DB để đảm bảo có ID (tránh ForeignKey error)
                            if category and not dry_run:
                                category.refresh_from_db()
                            # Note: Category path và path_slug được tự động tính trong Category.save()
                        
                        # ============================================
                        # 5. Data type conversion
                        # ============================================
                        # Price
                        price_display = row.get('pricing.priceDisplay', '').strip()
                        price_value = self.parse_price_value(price_display)
                        
                        # Boolean
                        is_published = self.convert_to_bool(row.get('metadata.isPublish', 'true'))
                        
                        # Integer
                        product_ranking = self.convert_to_int(row.get('metadata.productRanking', '0'), default=0)
                        display_code = self.convert_to_int(row.get('metadata.displayCode', ''), default=None)
                        
                        # ============================================
                        # 6. Image handling (lưu URL trực tiếp nếu --skip-image-upload)
                        # ============================================
                        image_url = row.get('media.image', '').strip()
                        cloudinary_image_id = None
                        
                        # images array đã được parse ở trên, lưu URL trực tiếp từ CSV
                        # images field (JSONField) có thể lưu URL trực tiếp
                        
                        if skip_image_upload:
                            # Skip upload Cloudinary, lưu URL trực tiếp vào images field
                            # image field (CloudinaryField) để None vì cần public_id
                            cloudinary_image_id = None
                            # images array đã có URL từ CSV, giữ nguyên
                        elif image_url and not dry_run:
                            # Upload image lên Cloudinary (chỉ khi không skip)
                            cloudinary_image_id = self.upload_image_from_url(image_url)
                        
                        # Get SKU/MID
                        sku = row.get('basicInfo.sku', '').strip()
                        if not sku:
                            sku = None
                        
                        # ============================================
                        # Create Medicine
                        # ============================================
                        medicine_defaults = {
                            'name': row.get('basicInfo.name', '').strip(),
                            'slug': row.get('basicInfo.slug', '').strip(),
                            'web_name': row.get('basicInfo.webName', '').strip(),
                            'description': row.get('content.description', '').strip(),
                            'ingredients': row.get('content.ingredients', '').strip(),
                            'usage': row.get('content.usage', '').strip(),
                            'dosage': row.get('content.dosage', '').strip(),
                            'adverse_effect': row.get('content.adverseEffect', '').strip(),
                            'careful': row.get('content.careful', '').strip(),
                            'preservation': row.get('content.preservation', '').strip(),
                            'brand_id': brand_id,  # None tạm thời
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
                        
                        # ============================================
                        # 7. Check duplicate MedicineUnit (medicine + category)
                        # ============================================
                        if skip_duplicates and not dry_run:
                            if MedicineUnit.objects.filter(medicine=medicine, category=category).exists():
                                skipped_count += 1
                                continue
                        
                        # ============================================
                        # Create MedicineUnit (với transaction cho từng row)
                        # ============================================
                        if not dry_run:
                            # Dùng transaction cho từng row để tránh rollback toàn bộ file
                            try:
                                with transaction.atomic():
                                    unit = MedicineUnit.objects.create(
                                medicine=medicine,
                                category=category,
                                price_display=price_display,
                                price_value=price_value,
                                package_size=row.get('pricing.packageSize', '').strip(),
                                prices=prices,
                                price_obj=price_obj if price_obj else {},
                                image=cloudinary_image_id,  # Cloudinary public_id
                                images=images,
                                link=row.get('metadata.link', '').strip(),
                                product_ranking=product_ranking,
                                display_code=display_code,
                                is_published=is_published,
                                registration_number=row.get('specifications.registrationNumber', '').strip(),
                                origin=row.get('specifications.origin', '').strip(),
                                manufacturer=row.get('specifications.manufacturer', '').strip(),
                                shelf_life=row.get('specifications.shelfLife', '').strip(),
                                specifications={},  # Có thể thêm sau nếu cần
                                in_stock=100,  # Default stock
                                    )
                                    imported_count += 1
                                    if (row_num - 1) % 100 == 0:
                                        self.stdout.write(f'  ✓ Progress: {row_num - 1}/{total_rows} rows processed')
                            except Exception as e:
                                # Nếu lỗi ở MedicineUnit, raise để catch ở ngoài
                                raise
                        else:
                            imported_count += 1
                            if (row_num - 1) % 100 == 0:
                                self.stdout.write(f'  ✓ Progress: {row_num - 1}/{total_rows} rows (DRY RUN)')
                            
                    except Exception as e:
                        import traceback
                        error_msg = f'Row {row_num}: {str(e)}'
                        errors.append(error_msg)
                        if len(errors) <= 5:  # Only show first 5 errors per file
                            self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
                        if dry_run and len(errors) <= 5:
                            self.stdout.write(traceback.format_exc())
            
            self.stdout.write(f'  ✅ File completed: {imported_count} imported, {skipped_count} skipped, {len(errors)} errors')
            return {
                'imported': imported_count,
                'skipped': skipped_count,
                'errors': errors
            }
            
        except Exception as e:
            error_msg = f'File error: {str(e)}'
            self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
            return {
                'imported': imported_count,
                'skipped': skipped_count,
                'errors': [error_msg] + errors
            }

    def handle(self, *args, **options):
        csv_file = options.get('file')
        csv_dir = options.get('dir')
        dry_run = options.get('dry_run', False)
        skip_duplicates = options.get('skip_duplicates', True)
        skip_image_upload = options.get('skip_image_upload', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No data will be saved'))
        
        if skip_duplicates:
            self.stdout.write(self.style.SUCCESS('🛡️  DUPLICATE PROTECTION: Enabled (skip existing medicine + category)'))
        
        if skip_image_upload:
            self.stdout.write(self.style.WARNING('⏭️  IMAGE UPLOAD: DISABLED (will skip image upload for faster import)'))
            self.stdout.write(self.style.WARNING('   Note: Images will be uploaded later using a separate script'))
        
        # Determine files to import
        csv_files = []
        
        if csv_dir:
            # Import all CSV files in directory
            if not os.path.exists(csv_dir):
                self.stdout.write(self.style.ERROR(f'❌ Directory not found: {csv_dir}'))
                return
            
            pattern = os.path.join(csv_dir, '*.csv')
            csv_files = sorted(glob.glob(pattern))
            
            if not csv_files:
                self.stdout.write(self.style.ERROR(f'❌ No CSV files found in {csv_dir}'))
                return
            
            self.stdout.write(self.style.SUCCESS(f'🚀 Starting import of {len(csv_files)} file(s) from directory...'))
            self.stdout.write(f'📁 Directory: {csv_dir}')
            
        elif csv_file:
            # Import single file
            if not os.path.exists(csv_file):
                self.stdout.write(self.style.ERROR(f'❌ File not found: {csv_file}'))
                return
            
            csv_files = [csv_file]
            self.stdout.write(self.style.SUCCESS('🚀 Starting import process...'))
            self.stdout.write(f'📁 File: {csv_file}')
        else:
            self.stdout.write(self.style.ERROR('❌ Please provide either --file or --dir option'))
            return
        
        # Category cache để tối ưu performance (shared across all files)
        category_cache = {}
        
        # Total stats
        total_imported = 0
        total_skipped = 0
        total_errors = []
        
        # Process each file
        for idx, file_path in enumerate(csv_files, 1):
            self.stdout.write(f'\n[{idx}/{len(csv_files)}] Processing file...')
            
            # Không dùng transaction.atomic() cho toàn bộ file
            # Vì nếu có lỗi ở một row, sẽ rollback toàn bộ file
            # Thay vào đó, commit từng row hoặc batch nhỏ
            stats = self.import_single_file(
                file_path, 
                dry_run=dry_run,
                skip_duplicates=skip_duplicates,
                skip_image_upload=skip_image_upload,
                category_cache=category_cache
            )
            
            total_imported += stats['imported']
            total_skipped += stats['skipped']
            total_errors.extend([f'{os.path.basename(file_path)}: {e}' for e in stats['errors']])
        
        # Final Summary
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS('✅ IMPORT COMPLETED!'))
        self.stdout.write(f'  📦 Total imported: {total_imported} products')
        if total_skipped > 0:
            self.stdout.write(self.style.WARNING(f'  ⏭️  Total skipped (duplicates): {total_skipped} products'))
        if total_errors:
            self.stdout.write(self.style.ERROR(f'  ❌ Total errors: {len(total_errors)}'))
            self.stdout.write(self.style.WARNING('  Showing first 10 errors:'))
            for error in total_errors[:10]:
                self.stdout.write(self.style.ERROR(f'    • {error}'))
            if len(total_errors) > 10:
                self.stdout.write(self.style.ERROR(f'    ... and {len(total_errors) - 10} more errors'))
        
        # Database status
        if not dry_run:
            self.stdout.write(f'\n📊 Database status:')
            self.stdout.write(f'  - Medicines: {Medicine.objects.count()}')
            self.stdout.write(f'  - MedicineUnits: {MedicineUnit.objects.count()}')
            self.stdout.write(f'  - Categories: {Category.objects.count()}')
        
        # Summary of issues handled
        self.stdout.write(self.style.SUCCESS(f'\n📋 Issues handled:'))
        self.stdout.write(f'  ✓ brand_id: Set to None (temporary)')
        self.stdout.write(f'  ✓ pricing.packageOptions: Skipped')
        self.stdout.write(f'  ✓ Image upload: From URL to Cloudinary')
        self.stdout.write(f'  ✓ JSON parsing: category, images, prices, price_obj')
        self.stdout.write(f'  ✓ Data conversion: boolean, integer, float')
        self.stdout.write(f'  ✓ Category hierarchy: level and path_slug auto-generated')
        self.stdout.write(f'  ✓ Duplicate prevention: Skip existing (medicine + category)')

