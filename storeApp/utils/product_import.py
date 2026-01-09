"""
Product Import Utilities - Reusable functions for CSV import

Functions:
    - import_csv_file: Main function to import CSV file
    - dry_run_import: Dry-run import without saving to DB
    - export_dry_run_to_json: Export dry-run results to JSON
    - get_import_statistics: Get statistics from import process
"""
import csv
import os
import json
from typing import Dict, List, Optional, Callable
from storeApp.utils import create_or_update_product_from_csv_row


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
    from storeApp.utils import (
        parse_json_field, parse_price_value,
        parse_package_options, convert_to_bool, convert_to_int,
        extract_country_from_text
    )
    
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
                
                prices = parse_json_field(row.get('pricing.prices', '[]'), default=[])
                
                price_display = row.get('pricing.priceDisplay', '').strip()
                price_value = parse_price_value(price_display)
                original_price = row.get('pricing.originalPrice', '').strip()
                original_price_value = parse_price_value(original_price) if original_price else None
                
                package_options_str = row.get('pricing.packageOptions', '').strip()
                package_options = parse_package_options(package_options_str) if package_options_str else []
                
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
                        "originalPrice": original_price or "",
                        "originalPriceValue": original_price_value if original_price_value is not None else None,
                        "packageSize": row.get('pricing.packageSize', '').strip(),
                        "packageOptions": package_options,
                        "prices": prices
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
