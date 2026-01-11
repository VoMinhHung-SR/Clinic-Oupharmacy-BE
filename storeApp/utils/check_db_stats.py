"""
Script để check tổng số lượng sản phẩm trong DB
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OUPharmacyManagementApp.settings')
django.setup()

from mainApp.models import Medicine, MedicineUnit, Category
from storeApp.models import Brand

if __name__ == '__main__':
    print('=' * 80)
    print('📊 DATABASE STATISTICS')
    print('=' * 80)
    print()
    
    # Medicine statistics
    total_medicines = Medicine.objects.count()
    medicines_with_mid = Medicine.objects.exclude(mid__isnull=True).exclude(mid='').count()
    medicines_without_mid = Medicine.objects.filter(mid__isnull=True) | Medicine.objects.filter(mid='')
    medicines_without_mid_count = medicines_without_mid.count()
    
    print('💊 MEDICINE STATISTICS:')
    print(f'   Total Medicines: {total_medicines:,}')
    print(f'   - With MID: {medicines_with_mid:,}')
    print(f'   - Without MID: {medicines_without_mid_count:,}')
    print()
    
    # MedicineUnit statistics
    total_units = MedicineUnit.objects.count()
    units_with_medicine = MedicineUnit.objects.exclude(medicine__isnull=True).count()
    units_with_category = MedicineUnit.objects.exclude(category__isnull=True).count()
    
    print('📦 MEDICINE UNIT STATISTICS:')
    print(f'   Total MedicineUnits: {total_units:,}')
    print(f'   - With Medicine: {units_with_medicine:,}')
    print(f'   - With Category: {units_with_category:,}')
    print()
    
    # Category statistics
    total_categories = Category.objects.count()
    print('🏷️  CATEGORY STATISTICS:')
    print(f'   Total Categories: {total_categories:,}')
    print()
    
    # Brand statistics
    total_brands = Brand.objects.count()
    print('🏭 BRAND STATISTICS:')
    print(f'   Total Brands: {total_brands:,}')
    print()
    
    # Sample of medicines without mid
    if medicines_without_mid_count > 0:
        print('⚠️  SAMPLE OF MEDICINES WITHOUT MID (first 5):')
        sample = Medicine.objects.filter(mid__isnull=True)[:5] | Medicine.objects.filter(mid='')[:5]
        for i, med in enumerate(sample[:5], 1):
            print(f'   {i}. ID: {med.id}, Name: {med.name[:60]}...' if len(med.name) > 60 else f'   {i}. ID: {med.id}, Name: {med.name}')
        if medicines_without_mid_count > 5:
            print(f'   ... and {medicines_without_mid_count - 5} more')
        print()
    
    # Sample of medicines with mid
    if medicines_with_mid > 0:
        print('✅ SAMPLE OF MEDICINES WITH MID (first 5):')
        sample = Medicine.objects.exclude(mid__isnull=True).exclude(mid='')[:5]
        for i, med in enumerate(sample, 1):
            print(f'   {i}. ID: {med.id}, MID: {med.mid}, Name: {med.name[:50]}...' if len(med.name) > 50 else f'   {i}. ID: {med.id}, MID: {med.mid}, Name: {med.name}')
        print()
    
    print('=' * 80)
