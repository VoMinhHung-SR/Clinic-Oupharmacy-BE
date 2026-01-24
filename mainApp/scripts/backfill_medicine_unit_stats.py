"""
Script backfill stats cho tất cả MedicineUnit cũ
Chạy: python manage.py shell < mainApp/scripts/backfill_medicine_unit_stats.py
"""
from mainApp.models import MedicineUnit, MedicineUnitStats
from django.db.models import F

print("🔄 Bắt đầu backfill MedicineUnitStats cho dữ liệu cũ...")

# Lấy tất cả MedicineUnit không có stats
medicine_units = MedicineUnit.objects.filter(stats__isnull=True)
total = medicine_units.count()

if total == 0:
    print("✅ Tất cả MedicineUnit đã có stats!")
else:
    print(f"📊 Tìm thấy {total} MedicineUnit cần backfill stats")
    
    # Batch create stats (efficient)
    stats_to_create = [
        MedicineUnitStats(unit=unit)
        for unit in medicine_units
    ]
    
    created = MedicineUnitStats.objects.bulk_create(stats_to_create, batch_size=1000)
    print(f"✅ Đã tạo {len(created)} MedicineUnitStats records")

print("✅ Backfill hoàn thành!")
