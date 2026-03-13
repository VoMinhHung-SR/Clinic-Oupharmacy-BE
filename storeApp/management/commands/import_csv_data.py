"""
Management command để import products từ CSV files
Kết hợp và refactor từ import_all_csv.py và import_products_from_csv.py

Chạy:
  - Import tất cả: python manage.py import_csv_data
  - Import một file: python manage.py import_csv_data --file storeApp/test/scraped-data-thuoc-mieng-dan-cao-xoa-dau-1-70.csv
  - Import thư mục: python manage.py import_csv_data --dir storeApp/test/data/thuoc
  - Dry-run: python manage.py import_csv_data --dir storeApp/test/data/thuoc --dry-run

Xử lý các vấn đề:
1. basicInfo.brand → Medicine.brand_id: Auto-map và tạo Brand nếu cần
2. pricing.packageOptions: Parse để tạo nhiều MedicineUnit (mỗi option = 1 unit với package_size riêng)
3. Image upload từ URL lên Cloudinary (có thể skip)
4. Parse JSON từ string CSV
5. Data type conversion
6. Category hierarchy với level và slug
7. Tránh duplicate: Check MedicineUnit với (medicine + category + package_size)
8. Batch processing cho performance
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
from mainApp.models import Medicine, MedicineUnit, Category, MedicineUnitStats
from storeApp.models import Brand
import cloudinary
import cloudinary.uploader


class Command(BaseCommand):
    help = 'Import products from CSV files (refactored version)'

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
            help='Skip duplicate MedicineUnits (same medicine + category + package_size). Default: True'
        )
        parser.add_argument(
            '--skip-image-upload',
            action='store_true',
            default=False,
            help='Skip image upload to Cloudinary (save original URL instead). Use this for faster import.'
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            default=False,
            help='Update existing MedicineUnits instead of skipping (use this to fix truncated data)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Batch size for bulk operations (default: 50)'
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

    def normalize_brand_name(self, brand_name):
        """Normalize brand name to handle variants (trim, remove extra spaces)"""
        if not brand_name:
            return None
        # Trim và normalize spaces
        normalized = ' '.join(brand_name.strip().split())
        return normalized if normalized else None

    def extract_country_from_text(self, text):
        """Extract country name from text (manufacturer or origin field)"""
        if not text:
            return None

        # Common country patterns in Vietnamese
        country_patterns = {
            'Úc': 'Úc',
            'Australia': 'Úc',
            'Pháp': 'Pháp',
            'France': 'Pháp',
            'Đức': 'Đức',
            'Germany': 'Đức',
            'Mỹ': 'Mỹ',
            'USA': 'Mỹ',
            'Hoa Kỳ': 'Mỹ',
            'Anh': 'Anh',
            'UK': 'Anh',
            'England': 'Anh',
            'Nhật': 'Nhật Bản',
            'Japan': 'Nhật Bản',
            'Hàn Quốc': 'Hàn Quốc',
            'Korea': 'Hàn Quốc',
            'Trung Quốc': 'Trung Quốc',
            'China': 'Trung Quốc',
            'Ấn Độ': 'Ấn Độ',
            'India': 'Ấn Độ',
            'Thái Lan': 'Thái Lan',
            'Thailand': 'Thái Lan',
            'Pakistan': 'Pakistan',
            'Parkistan': 'Pakistan',
            'Việt Nam': 'Việt Nam',
            'Vietnam': 'Việt Nam',
            'Canada': 'Canada',
            'Tây Ban Nha': 'Tây Ban Nha',
            'Spain': 'Tây Ban Nha',
            'Ý': 'Ý',
            'Italy': 'Ý',
            'Thụy Sĩ': 'Thụy Sĩ',
            'Switzerland': 'Thụy Sĩ',
            'Nga': 'Nga',
            'Russia': 'Nga',
            'Singapore': 'Singapore',
            'Malaysia': 'Malaysia',
            'Indonesia': 'Indonesia',
            'Đài Loan': 'Đài Loan',
            'Taiwan': 'Đài Loan',
            'Hồng Kông': 'Hồng Kông',
            'Hong Kong': 'Hồng Kông',
            'Bỉ': 'Bỉ',
            'Belgium': 'Bỉ',
            'Hà Lan': 'Hà Lan',
            'Netherlands': 'Hà Lan',
            'Hungary': 'Hungary',
            'Ba Lan': 'Ba Lan',
            'Poland': 'Ba Lan',
            'New Zealand': 'New Zealand',
        }

        text_lower = text.lower()
        for pattern, country in country_patterns.items():
            if pattern.lower() in text_lower:
                return country

        return None

    def parse_package_options(self, package_options_str, default_package_size=''):
        """
        Parse pricing.packageOptions để tạo list các package options
        Mỗi option sẽ tạo 1 MedicineUnit với package_size riêng

        Returns: list of dicts [{'package_size': str, 'price_display': str, 'price_value': float}, ...]
        """
        options = []

        if not package_options_str or not package_options_str.strip():
            # Nếu không có packageOptions, dùng default package_size
            if default_package_size:
                options.append({
                    'package_size': default_package_size,
                    'price_display': '',
                    'price_value': 0
                })
            return options

        # Thử parse như JSON array trước
        try:
            parsed = json.loads(package_options_str)
            if isinstance(parsed, list) and parsed:
                for item in parsed:
                    if isinstance(item, dict):
                        package_size = item.get('packageSize', '') or item.get('size', '') or default_package_size
                        price_display = item.get('priceDisplay', '') or item.get('price', '')
                        price_value = self.parse_price_value(price_display)
                        options.append({
                            'package_size': package_size,
                            'price_display': price_display,
                            'price_value': price_value
                        })
                return options
        except:
            pass

        # Nếu không phải JSON, parse như string với delimiter |
        parts = package_options_str.split('|')
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Parse pattern như "Hộp 29.000đ / Hộp (Hộp x 16g)"
            # Hoặc "29.000đ (Hộp x 16g)"
            package_size = default_package_size
            price_display = ''

            # Extract price
            price_match = re.search(r'(\d{1,3}(?:\.\d{3})*đ)', part)
            if price_match:
                price_display = price_match.group(1)
                price_value = self.parse_price_value(price_display)
            else:
                price_value = 0

            # Extract package size từ trong ngoặc
            size_match = re.search(r'\(([^)]+)\)', part)
            if size_match:
                package_size = size_match.group(1).strip()

            options.append({
                'package_size': package_size,
                'price_display': price_display,
                'price_value': price_value
            })

        # Nếu không parse được gì, dùng default
        if not options and default_package_size:
            options.append({
                'package_size': default_package_size,
                'price_display': '',
                'price_value': 0
            })

        return options

    def import_single_file(self, csv_file, dry_run=False, skip_duplicates=True, skip_image_upload=False, update_existing=False, category_cache=None, brand_cache=None):
        """
        Import một file CSV
        Returns: dict với stats {imported, skipped, errors}
        """
        if category_cache is None:
            category_cache = {}
        if brand_cache is None:
            brand_cache = {}

        file_name = os.path.basename(csv_file)
        self.stdout.write(f'\n📄 Processing: {file_name}')

        imported_count = 0
        skipped_count = 0
        errors = []
        units_to_create = []

        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows_list = list(reader)
                total_rows = len(rows_list)

                self.stdout.write(f'  📊 Total rows: {total_rows}')

                for row_num, row in enumerate(rows_list, start=2):
                    try:
                        # ============================================
                        # 1. Brand mapping: basicInfo.brand → Medicine.brand_id
                        # ============================================
                        brand_name_raw = row.get('basicInfo.brand', '').strip()
                        brand_id = None

                        if brand_name_raw:
                            brand_name = self.normalize_brand_name(brand_name_raw)

                            if brand_name:
                                if brand_cache is not None and brand_name in brand_cache:
                                    brand_id = brand_cache[brand_name]
                                else:
                                    # Extract country from manufacturer or origin
                                    manufacturer = row.get('specifications.manufacturer', '').strip()
                                    origin = row.get('specifications.origin', '').strip()

                                    country = None
                                    if manufacturer:
                                        country = self.extract_country_from_text(manufacturer)
                                    if not country and origin:
                                        country = self.extract_country_from_text(origin)

                                    if not dry_run:
                                        brand, created = Brand.objects.get_or_create(
                                            name=brand_name,
                                            defaults={'country': country, 'active': True}
                                        )
                                        brand_id = brand.id

                                        if brand_cache is not None:
                                            brand_cache[brand_name] = brand_id

                                        # Update country if found
                                        if not created and country and brand.country != country:
                                            brand.country = country
                                            brand.save(update_fields=['country'])

                        # ============================================
                        # 2. Parse package options để tạo nhiều units
                        # ============================================
                        default_package_size = row.get('pricing.packageSize', '').strip()
                        package_options_str = row.get('pricing.packageOptions', '').strip()

                        package_options = self.parse_package_options(package_options_str, default_package_size)

                        # Nếu không có options nào, tạo mặc định
                        if not package_options:
                            package_options = [{
                                'package_size': default_package_size or 'Default',
                                'price_display': row.get('pricing.priceDisplay', ''),
                                'price_value': self.parse_price_value(row.get('pricing.priceDisplay', ''))
                            }]

                        # ============================================
                        # 3. Parse JSON fields
                        # ============================================
                        category_json = row.get('category.category', '[]')
                        category_array = self.parse_json_field(category_json, default=[])

                        images_json = row.get('media.images', '[]')
                        images = self.parse_json_field(images_json, default=[])

                        specs_json = row.get('specifications.specifications', '{}')
                        specifications = self.parse_json_field(specs_json, default={})

                        # ============================================
                        # 4. Category hierarchy
                        # ============================================
                        category = None
                        if category_array:
                            category = Category.get_or_create_from_array(
                                category_array,
                                cache=category_cache
                            )
                            if category and not dry_run:
                                category.refresh_from_db()

                        # ============================================
                        # 5. Common data type conversion
                        # ============================================
                        is_published = self.convert_to_bool(row.get('metadata.isPublish', 'true'))
                        product_ranking = self.convert_to_int(row.get('metadata.productRanking', '0'), default=0)
                        display_code = self.convert_to_int(row.get('metadata.displayCode', ''), default=None)

                        # ============================================
                        # 6. Image handling
                        # ============================================
                        image_url = row.get('media.image', '').strip()
                        cloudinary_image_id = None

                        if skip_image_upload:
                            cloudinary_image_id = None
                        elif image_url and not dry_run:
                            cloudinary_image_id = self.upload_image_from_url(image_url)

                        # ============================================
                        # 7. Get or create Medicine
                        # ============================================
                        sku = row.get('basicInfo.sku', '').strip()
                        medicine_name = row.get('basicInfo.name', '').strip()

                        medicine = None
                        if sku:
                            medicine = Medicine.objects.filter(mid=sku).first()
                        if not medicine and medicine_name:
                            medicine = Medicine.objects.filter(name=medicine_name).first()

                        if not medicine:
                            medicine_defaults = {
                                'name': medicine_name,
                                'mid': sku,
                                'slug': row.get('basicInfo.slug', '').strip(),
                                'web_name': row.get('basicInfo.webName', '').strip(),
                                'description': row.get('content.description', '').strip(),
                                'ingredients': row.get('content.ingredients', '').strip(),
                                'usage': row.get('content.usage', '').strip(),
                                'dosage': row.get('content.dosage', '').strip(),
                                'adverse_effect': row.get('content.adverseEffect', '').strip(),
                                'careful': row.get('content.careful', '').strip(),
                                'preservation': row.get('content.preservation', '').strip(),
                                'brand_id': brand_id,
                            }

                            if sku:
                                medicine, _ = Medicine.objects.get_or_create(
                                    mid=sku,
                                    defaults=medicine_defaults
                                )
                            else:
                                medicine, _ = Medicine.objects.get_or_create(
                                    name=medicine_name,
                                    defaults=medicine_defaults
                                )
                        else:
                            # Update brand if needed
                            if brand_id and not medicine.brand_id:
                                medicine.brand_id = brand_id
                                medicine.save(update_fields=['brand_id'])

                        # ============================================
                        # 8. Create MedicineUnits cho mỗi package option
                        # ============================================
                        for option in package_options:
                            package_size = option['package_size'][:100] if option['package_size'] else ''
                            price_display = option['price_display'] or row.get('pricing.priceDisplay', '')
                            price_value = option['price_value'] or self.parse_price_value(price_display)

                            # Check duplicate: medicine + category + package_size
                            existing_unit = None
                            if not dry_run:
                                existing_unit = MedicineUnit.objects.filter(
                                    medicine=medicine,
                                    category=category,
                                    package_size=package_size
                                ).first()

                            if existing_unit:
                                if update_existing:
                                    # Update existing
                                    pass  # Will update below
                                elif skip_duplicates:
                                    skipped_count += 1
                                    continue

                            # Create or update unit
                            if not dry_run:
                                try:
                                    with transaction.atomic():
                                        # Truncate fields
                                        registration_number = row.get('specifications.registrationNumber', '').strip()[:100]
                                        origin = row.get('specifications.origin', '').strip()[:200]
                                        manufacturer = row.get('specifications.manufacturer', '').strip()
                                        shelf_life = row.get('specifications.shelfLife', '').strip()[:100]
                                        link = row.get('metadata.link', '').strip()[:500]

                                        if existing_unit and update_existing:
                                            # Update existing
                                            existing_unit.price_display = price_display
                                            existing_unit.price_value = price_value
                                            existing_unit.image = cloudinary_image_id
                                            existing_unit.images = images
                                            existing_unit.link = link
                                            existing_unit.product_ranking = product_ranking
                                            existing_unit.display_code = display_code
                                            existing_unit.is_published = is_published
                                            existing_unit.registration_number = registration_number
                                            existing_unit.origin = origin
                                            existing_unit.manufacturer = manufacturer
                                            existing_unit.shelf_life = shelf_life
                                            existing_unit.specifications = specifications
                                            existing_unit.save()

                                            MedicineUnitStats.objects.get_or_create(unit=existing_unit)
                                        else:
                                            # Create new
                                            unit = MedicineUnit.objects.create(
                                                medicine=medicine,
                                                category=category,
                                                price_display=price_display,
                                                price_value=price_value,
                                                package_size=package_size,
                                                image=cloudinary_image_id,
                                                images=images,
                                                link=link,
                                                product_ranking=product_ranking,
                                                display_code=display_code,
                                                is_published=is_published,
                                                registration_number=registration_number,
                                                origin=origin,
                                                manufacturer=manufacturer,
                                                shelf_life=shelf_life,
                                                specifications=specifications,
                                                in_stock=100,
                                            )
                                            MedicineUnitStats.objects.get_or_create(unit=unit)

                                        imported_count += 1

                                except Exception as e:
                                    raise
                            else:
                                imported_count += 1

                        if (row_num - 1) % 50 == 0:
                            self.stdout.write(f'  ✓ Progress: {row_num - 1}/{total_rows} rows processed')

                    except Exception as e:
                        import traceback
                        error_msg = f'Row {row_num}: {str(e)}'
                        errors.append(error_msg)
                        if len(errors) <= 5:
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
        update_existing = options.get('update_existing', False)
        self.batch_size = options.get('batch_size', 50)

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No data will be saved'))

        if skip_duplicates:
            self.stdout.write(self.style.SUCCESS('🛡️  DUPLICATE PROTECTION: Enabled (skip existing medicine + category + package_size)'))

        if skip_image_upload:
            self.stdout.write(self.style.WARNING('⏭️  IMAGE UPLOAD: DISABLED (will skip image upload for faster import)'))

        if update_existing:
            self.stdout.write(self.style.WARNING('🔄 UPDATE MODE: Will update existing MedicineUnits (overwrite data)'))

        # Determine files to import
        csv_files = []

        if csv_dir:
            if not os.path.exists(csv_dir):
                self.stdout.write(self.style.ERROR(f'❌ Directory not found: {csv_dir}'))
                return

            pattern = os.path.join(csv_dir, '**/*.csv')
            csv_files = sorted(glob.glob(pattern, recursive=True))

            if not csv_files:
                self.stdout.write(self.style.ERROR(f'❌ No CSV files found in {csv_dir}'))
                return

            self.stdout.write(self.style.SUCCESS(f'🚀 Starting import of {len(csv_files)} file(s) from directory...'))
            self.stdout.write(f'📁 Directory: {csv_dir}')

        elif csv_file:
            if not os.path.exists(csv_file):
                self.stdout.write(self.style.ERROR(f'❌ File not found: {csv_file}'))
                return

            csv_files = [csv_file]
            self.stdout.write(self.style.SUCCESS('🚀 Starting import process...'))
            self.stdout.write(f'📁 File: {csv_file}')
        else:
            # Default: import from storeApp/test
            test_dir = os.path.join('storeApp', 'test')
            if os.path.exists(test_dir):
                pattern = os.path.join(test_dir, 'scraped-data-*.csv')
                csv_files = sorted(glob.glob(pattern))

            if not csv_files:
                self.stdout.write(self.style.ERROR('❌ No CSV files found. Please provide --file or --dir option'))
                return

            self.stdout.write(self.style.SUCCESS(f'🚀 Starting import of {len(csv_files)} file(s) from default directory...'))

        # Caches
        category_cache = {}
        brand_cache = {}

        # Total stats
        total_imported = 0
        total_skipped = 0
        total_errors = []

        # Process each file
        for idx, file_path in enumerate(csv_files, 1):
            self.stdout.write(f'\n[{idx}/{len(csv_files)}] Processing file...')

            stats = self.import_single_file(
                file_path,
                dry_run=dry_run,
                skip_duplicates=skip_duplicates,
                skip_image_upload=skip_image_upload,
                update_existing=update_existing,
                category_cache=category_cache,
                brand_cache=brand_cache
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
            self.stdout.write(f'  - Brands: {Brand.objects.count()}')

        # Summary of issues handled
        self.stdout.write(self.style.SUCCESS(f'\n📋 Issues handled:'))
        self.stdout.write(f'  ✓ brand_id: Auto-mapped from basicInfo.brand (Brand created if not exists)')
        self.stdout.write(f'  ✓ pricing.packageOptions: Parsed to create multiple MedicineUnits')
        self.stdout.write(f'  ✓ Image upload: From URL to Cloudinary (optional)')
        self.stdout.write(f'  ✓ JSON parsing: category, images, specifications')
        self.stdout.write(f'  ✓ Data conversion: boolean, integer, float')
        self.stdout.write(f'  ✓ Category hierarchy: level and path_slug auto-generated')
        self.stdout.write(f'  ✓ Duplicate prevention: Skip existing (medicine + category + package_size)')