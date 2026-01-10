"""
Utility functions để hỗ trợ query cross-database và quản lý batch/notification
"""
import json
import re
from django.db import transaction
from mainApp.models import User, MedicineUnit, Medicine, Category
from .models import Order, Brand, MedicineBatch, Notification


def get_order_with_details(order_number):
    """
    Lấy Order kèm thông tin User và MedicineUnits
    
    Returns:
        dict: {
            'order': Order object,
            'user': User object hoặc None,
            'items': [
                {
                    'item': OrderItem,
                    'medicine_unit': MedicineUnit
                }
            ]
        }
    """
    try:
        order = Order.objects.select_related('shipping_method', 'payment_method').prefetch_related('items').get(
            order_number=order_number
        )
    except Order.DoesNotExist:
        return None
    
    result = {
        'order': order,
        'user': None,
        'items': []
    }
    
    # Lấy User từ default database
    if order.user_id:
        try:
            result['user'] = User.objects.using('default').get(id=order.user_id)
        except User.DoesNotExist:
            pass
    
    # Lấy MedicineUnits từ default database
    medicine_unit_ids = [item.medicine_unit_id for item in order.items.all()]
    if medicine_unit_ids:
        medicine_units = {
            mu.id: mu for mu in MedicineUnit.objects.using('default').select_related('medicine', 'category').filter(
                id__in=medicine_unit_ids
            )
        }
        
        for item in order.items.all():
            medicine_unit = medicine_units.get(item.medicine_unit_id)
            result['items'].append({
                'item': item,
                'medicine_unit': medicine_unit
            })
    
    return result


def get_medicine_unit_with_brand(medicine_unit_id):
    """
    Lấy MedicineUnit kèm thông tin Brand nếu có
    
    Returns:
        dict: {
            'medicine_unit': MedicineUnit,
            'brand': Brand object hoặc None
        }
    """
    try:
        medicine_unit = MedicineUnit.objects.using('default').select_related('medicine', 'category').get(
            id=medicine_unit_id
        )
    except MedicineUnit.DoesNotExist:
        return None
    
    result = {
        'medicine_unit': medicine_unit,
        'brand': None
    }
    
    # Lấy Brand từ store database
    if medicine_unit.brand_id:
        try:
            result['brand'] = Brand.objects.get(id=medicine_unit.brand_id)
        except Brand.DoesNotExist:
            pass
    
    return result


def get_medicine_batches_with_details(medicine_unit_id):
    """
    Lấy tất cả batches của một MedicineUnit kèm thông tin chi tiết
    
    Returns:
        list: List of MedicineBatch objects với thông tin expiry status
    """
    batches = MedicineBatch.objects.filter(
        medicine_unit_id=medicine_unit_id,
        active=True
    ).order_by('expiry_date', 'import_date')
    
    return batches


def get_near_expiry_batches(days_threshold=30):
    """
    Lấy tất cả batches sắp hết hạn
    
    Args:
        days_threshold: Số ngày trước khi hết hạn để cảnh báo (default: 30)
    
    Returns:
        QuerySet: MedicineBatch objects sắp hết hạn
    """
    from django.utils import timezone
    from datetime import timedelta
    
    expiry_date_threshold = timezone.now().date() + timedelta(days=days_threshold)
    
    return MedicineBatch.objects.filter(
        active=True,
        remaining_quantity__gt=0,
        expiry_date__lte=expiry_date_threshold,
        expiry_date__gte=timezone.now().date()
    ).order_by('expiry_date')


def get_unread_notifications_count():
    """Lấy số lượng thông báo chưa đọc"""
    return Notification.objects.filter(is_read=False).count()


def get_unread_notifications(limit=10):
    """
    Lấy danh sách thông báo chưa đọc
    
    Args:
        limit: Số lượng thông báo tối đa (default: 10)
    
    Returns:
        QuerySet: Notification objects chưa đọc
    """
    return Notification.objects.filter(is_read=False).order_by('-created_date')[:limit]


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
        prices = parse_json_field(row.get('pricing.prices', '[]'), default=[])
        package_options_str = row.get('pricing.packageOptions', '').strip()
        package_options = parse_package_options(package_options_str) if package_options_str else []
        
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
        # 6. Create/Update Medicine - Enhanced: Tìm bằng sku/mid, update brand cùng
        # ============================================
        medicine = None
        medicine_created = False
        
        # Priority 1: Tìm bằng sku/mid (nếu có)
        if sku:
            medicine = Medicine.objects.filter(mid=sku).first()
        
        # Priority 2: Tìm bằng name (nếu chưa tìm thấy)
        if not medicine and medicine_name:
            medicine = Medicine.objects.filter(name=medicine_name).first()
        
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
            
            if not dry_run:
                if sku:
                    try:
                        medicine, medicine_created = Medicine.objects.get_or_create(
                            mid=sku,
                            defaults=medicine_defaults
                        )
                    except Exception:
                        medicine = Medicine.objects.filter(name=medicine_name).first()
                        if not medicine:
                            medicine, medicine_created = Medicine.objects.get_or_create(
                                name=medicine_name,
                                defaults=medicine_defaults
                            )
                else:
                    medicine, medicine_created = Medicine.objects.get_or_create(
                        name=medicine_name,
                        defaults=medicine_defaults
                    )
        else:
            # Update existing Medicine - Update brand_id cùng với medicine
            if not dry_run:
                update_fields = []
                
                # Update brand_id nếu có brand_id mới và khác với brand_id hiện tại
                if brand_id and medicine.brand_id != brand_id:
                    medicine.brand_id = brand_id
                    update_fields.append('brand_id')
                
                # Có thể thêm các fields khác cần update ở đây nếu cần
                # Ví dụ: update mid nếu chưa có
                if sku and not medicine.mid:
                    medicine.mid = sku
                    update_fields.append('mid')
                
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
        existing_unit = None
        if not dry_run:
            existing_unit = MedicineUnit.objects.filter(medicine=medicine, category=category).first()
        
        if existing_unit and not update_existing:
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
                    'original_price': original_price if original_price else None,
                    'original_price_value': original_price_value,
                    'package_size': package_size,
                    'package_options': package_options,
                    'prices': prices,
                    'image': None,  # Skip image (CloudinaryField) - luôn giữ default để tránh overload upload
                    'images': images,  # Chỉ import vào images (JSONField) - array of URLs
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

