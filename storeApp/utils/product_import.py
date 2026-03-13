"""
Product Import Utilities - Reusable functions for CSV import

Functions:
    - Helper functions: parse_price_value, parse_json_field, convert_to_int, etc.
    - create_or_update_product_from_csv_row: Main function to create/update product from CSV row
    - import_csv_file: Main function to import CSV file
    - dry_run_import: Dry-run import without saving to DB
    - export_dry_run_to_json: Export dry-run results to JSON
    - print_import_statistics: Print import statistics
"""
import csv
import os
import json
import re
from typing import Dict, Optional, Callable
from django.db import transaction
from mainApp.models import MedicineUnit, Medicine, Category
from storeApp.models import Brand


# ============================================
# Product Import Helper Functions
# ============================================

def parse_price_value(price_display):
    """Parse price_display string to float value"""
    if not price_display:
        return 0
    price_str = price_display.replace('đ', '').replace('.', '').strip()
    try:
        return float(price_str)
    except (ValueError, TypeError):
        return 0


def parse_json_field(json_str, default=None):
    """Parse JSON field từ CSV string"""
    if default is None:
        default = [] if isinstance(default, list) else {}
    
    if not json_str or not json_str.strip():
        return default
    
    try:
        parsed = json.loads(json_str)
        return parsed if parsed else default
    except (json.JSONDecodeError, TypeError):
        return default


def convert_to_int(value, default=0):
    """Convert string to integer"""
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def convert_to_bool(value, default=False):
    """Convert string to boolean"""
    if not value:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ('true', '1', 'yes', 'on')


def normalize_brand_name(brand_name):
    """Normalize brand name to handle variants"""
    if not brand_name:
        return None
    normalized = ' '.join(brand_name.strip().split())
    return normalized if normalized else None


def extract_country_from_text(text):
    """Extract country name from text (manufacturer or origin field)"""
    if not text:
        return None
    
    country_patterns = {
        'Úc': 'Australia', 'Australia': 'Australia',
        'Pháp': 'France', 'France': 'France',
        'Đức': 'Germany', 'Germany': 'Germany',
        'Mỹ': 'USA', 'USA': 'USA', 'Hoa Kỳ': 'USA',
        'Anh': 'UK', 'UK': 'UK', 'United Kingdom': 'UK', 'England': 'UK',
        'Nhật': 'Japan', 'Japan': 'Japan',
        'Hàn Quốc': 'South Korea', 'Korea': 'South Korea',
        'Trung Quốc': 'China', 'China': 'China',
        'Ấn Độ': 'India', 'India': 'India',
        'Thái Lan': 'Thailand', 'Thailand': 'Thailand',
        'Pakistan': 'Pakistan', 'Parkistan': 'Pakistan',
        'Việt Nam': 'Vietnam', 'Vietnam': 'Vietnam',
        'Hungary': 'Hungary', 'Hungari': 'Hungary',
        'Sweden': 'Sweden', 'Thụy Điển': 'Sweden',
    }
    
    text_lower = text.lower()
    for pattern, country in country_patterns.items():
        if pattern.lower() in text_lower:
            return country
    
    return None


def parse_package_options(package_options_str):
    """
    Parse packageOptions từ string format sang JSON array
    Format: "Hộp 159.080đ / Hộp (Hộp 2 Vỉ x 10 Ống x 5ml) | ..."
    Returns: JSON array hoặc empty list
    """
    if not package_options_str or not package_options_str.strip():
        return []
    
    # Nếu đã là JSON array string, parse trực tiếp
    if package_options_str.strip().startswith('['):
        return parse_json_field(package_options_str, default=[])
    
    # Parse từ string format: "Unit Price / Unit (Spec) | ..."
    options = []
    parts = package_options_str.split('|')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Extract unit, price, spec từ format: "Unit Price / Unit (Spec)"
        # Ví dụ: "Hộp 159.080đ / Hộp (Hộp 2 Vỉ x 10 Ống x 5ml)"
        match = re.match(r'(.+?)\s+([\d.,]+đ)\s*/\s*(.+?)(?:\s*\((.+?)\))?', part)
        if match:
            unit_display = match.group(1).strip()
            price = match.group(2).strip()
            unit = match.group(3).strip()
            spec = match.group(4).strip() if match.group(4) else ''
            
            options.append({
                'unit': unit,
                'unitDisplay': unit_display,
                'price': price,
                'priceValue': parse_price_value(price),
                'specification': spec
            })
    
    return options


def create_or_update_product_from_csv_row(row, category_cache=None, brand_cache=None, 
                                         skip_image_upload=False, update_existing=False, 
                                         dry_run=False, image_upload_func=None):
    """
    Helper function để create hoặc update product từ CSV row
    
    Args:
        row: Dict từ CSV row (csv.DictReader)
        category_cache: Dict để cache categories {(parent_id, slug): category}
        brand_cache: Dict để cache brands {brand_name: brand_id}
        skip_image_upload: DEPRECATED - Image field (CloudinaryField) luôn được skip để tránh overload
        update_existing: Update existing MedicineUnit thay vì skip
        dry_run: Chỉ validate, không save vào DB
        image_upload_func: DEPRECATED - Không sử dụng nữa, images được lưu trực tiếp vào JSONField
    
    Returns:
        dict: {
            'success': bool,
            'action': 'created' | 'updated' | 'skipped',
            'medicine': Medicine object hoặc None,
            'medicine_unit': MedicineUnit object hoặc None,
            'error': str hoặc None
        }
    
    Note:
        - image field (CloudinaryField) luôn giữ default (None) để tránh overload upload
        - Chỉ import vào images field (JSONField) - array of URLs
        - Nếu CSV có cả media.image và media.images, cả hai đều được thêm vào images array
    """
    if category_cache is None:
        category_cache = {}
    if brand_cache is None:
        brand_cache = {}
    
    try:
        # ============================================
        # 1. Parse Brand - Enhanced: Check CSV có country field riêng
        # ============================================
        brand_name_raw = row.get('basicInfo.brand', '').strip()
        brand_id = None
        
        if brand_name_raw:
            brand_name = normalize_brand_name(brand_name_raw)
            if brand_name:
                # Parse country trước để có thể update brand country
                country = None
                country_from_csv = (
                    row.get('basicInfo.country', '').strip() or
                    row.get('brand.country', '').strip() or
                    row.get('specifications.country', '').strip()
                )
                
                if country_from_csv:
                    # Nếu CSV có country field riêng, normalize nó
                    country = extract_country_from_text(country_from_csv) or country_from_csv
                else:
                    # Fallback: Extract từ origin trước (rõ ràng hơn), sau đó manufacturer
                    origin = row.get('specifications.origin', '').strip()
                    manufacturer = row.get('specifications.manufacturer', '').strip()
                    
                    # Priority 1: Extract từ origin
                    if origin:
                        country = extract_country_from_text(origin)
                    # Priority 2: Extract từ manufacturer nếu origin không có
                    if not country and manufacturer:
                        country = extract_country_from_text(manufacturer)
                
                if brand_name in brand_cache:
                    brand_id = brand_cache[brand_name]
                    # Update brand country nếu có country mới (kể cả khi brand đã trong cache)
                    if not dry_run and country:
                        try:
                            brand = Brand.objects.get(id=brand_id)
                            if not brand.country or brand.country != country:
                                brand.country = country
                                brand.save(update_fields=['country'])
                        except Brand.DoesNotExist:
                            pass
                elif not dry_run:
                    # Get or create Brand, update country nếu có
                    brand, brand_created = Brand.objects.get_or_create(
                        name=brand_name,
                        defaults={'country': country, 'active': True}
                    )
                    
                    # Update country nếu brand đã tồn tại nhưng chưa có country và có country mới
                    if not brand_created and not brand.country and country:
                        brand.country = country
                        brand.save(update_fields=['country'])
                    # Update country nếu brand đã tồn tại và country mới khác với country hiện tại
                    elif not brand_created and country and brand.country != country:
                        brand.country = country
                        brand.save(update_fields=['country'])
                    
                    brand_id = brand.id
                    brand_cache[brand_name] = brand_id
        
        # ============================================
        # 2. Parse JSON fields
        # ============================================
        category_array = parse_json_field(row.get('category.category', '[]'), default=[])
        images = parse_json_field(row.get('media.images', '[]'), default=[])
        
        # ============================================
        # 2.1. Handle images: Skip image (CloudinaryField), only import to images (JSONField)
        # ============================================
        # Nếu CSV có media.image, thêm vào đầu images array
        # image field (CloudinaryField) sẽ luôn giữ default (None) để tránh overload upload
        image_url = row.get('media.image', '').strip()
        if image_url:
            # Thêm image_url vào đầu images array nếu chưa có
            if not isinstance(images, list):
                images = []
            # Chỉ thêm nếu chưa có trong images array
            if image_url not in images:
                images.insert(0, image_url)
        
        # ============================================
        # 3. Parse Category
        # ============================================
        category = None
        if category_array:
            category = Category.get_or_create_from_array(category_array, cache=category_cache)
            if category and not dry_run:
                category.refresh_from_db()
        
        # ============================================
        # 4. Parse Pricing
        # ============================================
        price_display = row.get('pricing.priceDisplay', '').strip()
        price_value = parse_price_value(price_display)
        original_price = row.get('pricing.originalPrice', '').strip()
        original_price_value = parse_price_value(original_price) if original_price else None
        
        # ============================================
        # 5. Parse other fields
        # ============================================
        sku = row.get('basicInfo.sku', '').strip() or None
        medicine_name = row.get('basicInfo.name', '').strip()
        slug = row.get('basicInfo.slug', '').strip()
        web_name = row.get('basicInfo.webName', '').strip()
        
        is_published = convert_to_bool(row.get('metadata.isPublish', 'true'), default=True)
        product_ranking = convert_to_int(row.get('metadata.productRanking', '0'), default=0)
        display_code = convert_to_int(row.get('metadata.displayCode', ''), default=None)
        is_hot = convert_to_bool(row.get('metadata.isHot', 'false'), default=False)  # Optional field
        
        package_size = row.get('pricing.packageSize', '').strip()[:100] if row.get('pricing.packageSize') else ''
        registration_number = row.get('specifications.registrationNumber', '').strip()[:100] if row.get('specifications.registrationNumber') else ''
        origin = row.get('specifications.origin', '').strip()[:200] if row.get('specifications.origin') else ''
        manufacturer = row.get('specifications.manufacturer', '').strip()
        shelf_life = row.get('specifications.shelfLife', '').strip()[:100] if row.get('specifications.shelfLife') else ''
        # Parse specifications JSON object if exists
        specifications_json = parse_json_field(row.get('specifications.specifications', '{}'), default={})
        link = row.get('metadata.link', '').strip()[:500] if row.get('metadata.link') else ''
        
        # ============================================
        # 6. Create/Update Medicine - Enhanced: Tìm bằng sku/mid trước, double-check logic
        # ============================================
        medicine = None
        medicine_created = False
        
        # Priority 1: Tìm bằng sku/mid (nếu có)
        if sku:
            medicine = Medicine.objects.filter(mid=sku).first()
        
        # Priority 2: Tìm bằng name (chỉ khi không có sku hoặc không tìm thấy bằng mid)
        # Lưu ý: Nếu tìm thấy bằng name nhưng medicine đó đã có mid khác, không nên update
        if not medicine and medicine_name:
            medicine_by_name = Medicine.objects.filter(name=medicine_name).first()
            # Chỉ dùng medicine tìm được bằng name nếu:
            # - Medicine đó chưa có mid (mid=None hoặc empty)
            # - Hoặc medicine đó có mid trùng với sku hiện tại (trường hợp hiếm)
            if medicine_by_name:
                if not medicine_by_name.mid or (sku and medicine_by_name.mid == sku):
                    medicine = medicine_by_name
                # Nếu medicine_by_name có mid khác với sku, không dùng (có thể là medicine khác)
        
        if not medicine:
            # Create new Medicine
            medicine_defaults = {
                'name': medicine_name,
                'slug': slug,
                'web_name': web_name,
                'description': row.get('content.description', '').strip(),
                'ingredients': row.get('content.ingredients', '').strip(),
                'usage': row.get('content.usage', '').strip(),
                'dosage': row.get('content.dosage', '').strip(),
                'adverse_effect': row.get('content.adverseEffect', '').strip(),
                'careful': row.get('content.careful', '').strip(),
                'preservation': row.get('content.preservation', '').strip(),
                'brand_id': brand_id,
            }
            
            # Luôn set mid nếu có sku
            if sku:
                medicine_defaults['mid'] = sku
            
            if not dry_run:
                if sku:
                    # Double-check: Đảm bảo không có medicine nào khác đã có mid này
                    existing_with_mid = Medicine.objects.filter(mid=sku).first()
                    if existing_with_mid:
                        # Nếu đã tồn tại medicine với mid này, dùng nó
                        medicine = existing_with_mid
                        medicine_created = False
                    else:
                        # Tạo mới với mid
                        try:
                            medicine, medicine_created = Medicine.objects.get_or_create(
                                mid=sku,
                                defaults=medicine_defaults
                            )
                        except Exception as e:
                            # Nếu có lỗi (ví dụ: unique constraint violation), thử tìm lại
                            medicine = Medicine.objects.filter(mid=sku).first()
                            if not medicine:
                                # Nếu vẫn không tìm thấy, thử tạo bằng name (fallback)
                                medicine, medicine_created = Medicine.objects.get_or_create(
                                    name=medicine_name,
                                    defaults=medicine_defaults
                                )
                else:
                    # Không có sku, tạo bằng name
                    medicine, medicine_created = Medicine.objects.get_or_create(
                        name=medicine_name,
                        defaults=medicine_defaults
                    )
        else:
            # Update existing Medicine - Update brand_id và mid nếu cần
            if not dry_run:
                update_fields = []
                
                # Update brand_id nếu có brand_id mới và khác với brand_id hiện tại
                if brand_id and medicine.brand_id != brand_id:
                    medicine.brand_id = brand_id
                    update_fields.append('brand_id')
                
                # Update mid nếu chưa có mid và có sku
                # Double-check: Đảm bảo sku không conflict với medicine khác
                if sku and not medicine.mid:
                    # Check xem có medicine nào khác đã có mid này chưa
                    existing_with_mid = Medicine.objects.filter(mid=sku).exclude(id=medicine.id).first()
                    if not existing_with_mid:
                        medicine.mid = sku
                        update_fields.append('mid')
                    # Nếu đã có medicine khác với mid này, không update (tránh conflict)
                
                if update_fields:
                    medicine.save(update_fields=update_fields)
        
        # In dry_run mode, medicine might be None if it doesn't exist in DB
        # That's OK - we just validate the data without creating it
        if not medicine and not dry_run:
            if not medicine_name:
                return {
                    'success': False,
                    'action': 'skipped',
                    'medicine': None,
                    'medicine_unit': None,
                    'error': 'Medicine name is required'
                }
            # This shouldn't happen if logic is correct, but just in case
            return {
                'success': False,
                'action': 'skipped',
                'medicine': None,
                'medicine_unit': None,
                'error': 'Failed to create or find Medicine'
            }
        
        # ============================================
        # 7. Check existing MedicineUnit
        # ============================================
        # Trong dry_run mode, vẫn cần query DB để xác định đúng action (created/updated)
        existing_unit = None
        if medicine:  # Chỉ query nếu đã có medicine (từ DB hoặc vừa tạo)
            existing_unit = MedicineUnit.objects.filter(medicine=medicine, category=category).first()
        
        if existing_unit and not update_existing:
            # Chỉ skip khi không phải dry_run (vì dry_run cần return action để thống kê)
            if not dry_run:
                return {
                    'success': True,
                    'action': 'skipped',
                    'medicine': medicine,
                    'medicine_unit': existing_unit,
                    'error': None
                }
        
        # ============================================
        # 8. Create/Update MedicineUnit
        # ============================================
        if not dry_run:
            with transaction.atomic():
                unit_data = {
                    'medicine': medicine,
                    'category': category,
                    'price_display': price_display,
                    'price_value': price_value,
                    'original_price_value': original_price_value,
                    'package_size': package_size,
                    'image': None,  # Skip image (CloudinaryField)
                    'images': images,  # Chỉ import vào images (JSONField)
                    'link': link,
                    'product_ranking': product_ranking,
                    'display_code': display_code,
                    'is_published': is_published,
                    'is_hot': is_hot,
                    'registration_number': registration_number,
                    'origin': origin,
                    'manufacturer': manufacturer,
                    'shelf_life': shelf_life,
                    'specifications': specifications_json,  # Parse từ CSV nếu có
                    'in_stock': 100,  # Default stock
                }
                
                if existing_unit and update_existing:
                    # Update existing
                    for key, value in unit_data.items():
                        if key != 'medicine':  # Don't update FK
                            setattr(existing_unit, key, value)
                    existing_unit.save()
                    return {
                        'success': True,
                        'action': 'updated',
                        'medicine': medicine,
                        'medicine_unit': existing_unit,
                        'error': None
                    }
                else:
                    # Create new
                    unit = MedicineUnit.objects.create(**unit_data)
                    return {
                        'success': True,
                        'action': 'created',
                        'medicine': medicine,
                        'medicine_unit': unit,
                        'error': None
                    }
        else:
            # Dry run - return success without saving
            return {
                'success': True,
                'action': 'created' if not existing_unit else 'updated',
                'medicine': None,
                'medicine_unit': None,
                'error': None
            }
    
    except Exception as e:
        return {
            'success': False,
            'action': 'error',
            'medicine': None,
            'medicine_unit': None,
            'error': str(e)
        }


# ============================================
# High-level Import Functions
# ============================================

def import_csv_file(
    csv_file_path: str,
    skip_image_upload: bool = True,
    update_existing: bool = False,
    dry_run: bool = False,
    image_upload_func: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None
) -> Dict[str, int]:
    """
    Import products from CSV file using helper function
    
    Args:
        csv_file_path: Path to CSV file
        skip_image_upload: Skip Cloudinary image upload (always True - images go to JSONField)
        update_existing: Update existing MedicineUnit instead of skipping
        dry_run: Only validate, don't save to DB
        image_upload_func: DEPRECATED - Not used anymore
        progress_callback: Optional callback function(row_num, total, stats) for progress updates
    
    Returns:
        dict: {
            'total': int,
            'created': int,
            'updated': int,
            'skipped': int,
            'errors': int
        }
    """
    category_cache = {}
    brand_cache = {}
    
    stats = {
        'total': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }
    
    if not os.path.exists(csv_file_path):
        raise FileNotFoundError(f'CSV file not found: {csv_file_path}')
    
    with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        stats['total'] = len(rows)
        
        for row_num, row in enumerate(rows, start=1):
            result = create_or_update_product_from_csv_row(
                row=row,
                category_cache=category_cache,
                brand_cache=brand_cache,
                skip_image_upload=skip_image_upload,
                update_existing=update_existing,
                dry_run=dry_run,
                image_upload_func=image_upload_func
            )
            
            if result['success']:
                if result['action'] == 'created':
                    stats['created'] += 1
                elif result['action'] == 'updated':
                    stats['updated'] += 1
                elif result['action'] == 'skipped':
                    stats['skipped'] += 1
            else:
                stats['errors'] += 1
                if progress_callback:
                    progress_callback(row_num, stats['total'], stats, error=result.get('error'))
            
            # Progress callback
            if progress_callback and row_num % 10 == 0:
                progress_callback(row_num, stats['total'], stats)
    
    return stats


def dry_run_import(csv_file_path: str, update_existing: bool = True) -> Dict[str, int]:
    """
    Dry-run import to get statistics without saving to DB
    
    Args:
        csv_file_path: Path to CSV file
        update_existing: Enable update mode for statistics
    
    Returns:
        dict: Statistics dictionary
    """
    return import_csv_file(
        csv_file_path=csv_file_path,
        skip_image_upload=True,
        update_existing=update_existing,
        dry_run=True
    )


def export_dry_run_to_json(
    csv_file_path: str,
    output_json_path: str = 'demo.json',
    max_rows: Optional[int] = None
) -> int:
    """
    Export dry-run results to JSON file for review
    
    Args:
        csv_file_path: Path to CSV file
        output_json_path: Path to output JSON file
        max_rows: Maximum rows to process (None = all)
    
    Returns:
        int: Number of rows processed
    """
    if not os.path.exists(csv_file_path):
        raise FileNotFoundError(f'CSV file not found: {csv_file_path}')
    
    category_cache = {}
    brand_cache = {}
    results = []
    
    with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        total_rows = len(rows)
        
        if max_rows:
            rows = rows[:max_rows]
        
        for idx, row in enumerate(rows, 1):
            # Call helper function với dry_run=True
            result = create_or_update_product_from_csv_row(
                row=row,
                category_cache=category_cache,
                brand_cache=brand_cache,
                skip_image_upload=True,
                update_existing=False,
                dry_run=True,
                image_upload_func=None
            )
            
            if result['success']:
                # Build JSON structure giống data.json
                category_array = parse_json_field(row.get('category.category', '[]'), default=[])
                images = parse_json_field(row.get('media.images', '[]'), default=[])
                image_url = row.get('media.image', '').strip()
                if image_url and image_url not in images:
                    images.insert(0, image_url)
                
                price_display = row.get('pricing.priceDisplay', '').strip()
                price_value = parse_price_value(price_display)
                original_price = row.get('pricing.originalPrice', '').strip()
                original_price_value = parse_price_value(original_price) if original_price else None
                
                # Extract brand info
                brand_name = row.get('basicInfo.brand', '').strip()
                origin = row.get('specifications.origin', '').strip()
                manufacturer = row.get('specifications.manufacturer', '').strip()
                
                # Extract country
                country = None
                country_from_csv = (
                    row.get('basicInfo.country', '').strip() or
                    row.get('brand.country', '').strip() or
                    row.get('specifications.country', '').strip()
                )
                
                if country_from_csv:
                    country = extract_country_from_text(country_from_csv) or country_from_csv
                else:
                    if origin:
                        country = extract_country_from_text(origin)
                    if not country and manufacturer:
                        country = extract_country_from_text(manufacturer)
                
                json_item = {
                    "basicInfo": {
                        "name": row.get('basicInfo.name', '').strip(),
                        "sku": row.get('basicInfo.sku', '').strip(),
                        "brand": brand_name,
                        "webName": row.get('basicInfo.webName', '').strip(),
                        "slug": row.get('basicInfo.slug', '').strip()
                    },
                    "pricing": {
                        "price": row.get('pricing.price', '').strip() or price_display,
                        "priceDisplay": price_display,
                        "priceValue": price_value,
                        "originalPriceValue": original_price_value if original_price_value is not None else None,
                        "packageSize": row.get('pricing.packageSize', '').strip()
                    },
                    "rating": {
                        "rating": row.get('rating.rating', '').strip() or "",
                        "reviewCount": row.get('rating.reviewCount', '').strip() or "",
                        "commentCount": row.get('rating.commentCount', '').strip() or "",
                        "reviews": row.get('rating.reviews', '').strip() or ""
                    },
                    "category": {
                        "category": category_array,
                        "categoryPath": row.get('category.categoryPath', '').strip(),
                        "categorySlug": row.get('category.categorySlug', '').strip()
                    },
                    "media": {
                        "image": "",  # Skipped - always empty
                        "images": images
                    },
                    "content": {
                        "description": row.get('content.description', '').strip(),
                        "ingredients": row.get('content.ingredients', '').strip(),
                        "usage": row.get('content.usage', '').strip(),
                        "dosage": row.get('content.dosage', '').strip(),
                        "adverseEffect": row.get('content.adverseEffect', '').strip(),
                        "careful": row.get('content.careful', '').strip(),
                        "preservation": row.get('content.preservation', '').strip()
                    },
                    "specifications": {
                        "registrationNumber": row.get('specifications.registrationNumber', '').strip(),
                        "origin": origin,
                        "manufacturer": manufacturer,
                        "shelfLife": row.get('specifications.shelfLife', '').strip()
                    },
                    "_brandInfo": {
                        "brandName": brand_name,
                        "origin": origin,
                        "manufacturer": manufacturer[:100] if manufacturer else "",
                        "extractedCountry": country,
                        "note": "Brand country sẽ được extract từ origin/manufacturer trong helper function"
                    },
                    "metadata": {
                        "link": row.get('metadata.link', '').strip(),
                        "productRanking": convert_to_int(row.get('metadata.productRanking', '0'), default=0),
                        "displayCode": convert_to_int(row.get('metadata.displayCode', ''), default=None),
                        "isPublish": convert_to_bool(row.get('metadata.isPublish', 'true'), default=True),
                        "isHot": convert_to_bool(row.get('metadata.isHot', 'false'), default=False)
                    }
                }
                
                results.append(json_item)
    
    # Write to JSON file
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    return len(results)


def print_import_statistics(stats: Dict[str, int], csv_file: str = ''):
    """
    Print import statistics in a formatted way
    
    Args:
        stats: Statistics dictionary from import_csv_file
        csv_file: Optional CSV file path for display
    """
    print('=' * 80)
    print('📊 IMPORT STATISTICS')
    print('=' * 80)
    if csv_file:
        print(f'📄 CSV File: {csv_file}')
    print(f'📊 Total Rows: {stats["total"]}')
    print()
    print('📈 RESULTS:')
    print(f'  ✅ Created: {stats["created"]}')
    print(f'  🔄 Updated: {stats["updated"]}')
    print(f'  ⏭️  Skipped: {stats["skipped"]}')
    print(f'  ❌ Errors: {stats["errors"]}')
    print('=' * 80)
