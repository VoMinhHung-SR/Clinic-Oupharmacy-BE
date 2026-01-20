"""
Test script to verify MedicineUnitStats implementation
Run: python3 manage.py shell < test_medicine_unit_stats.py
"""
from mainApp.models import MedicineUnit, MedicineUnitStats

print("=" * 60)
print("MedicineUnitStats Verification")
print("=" * 60)

# Count total units
total_units = MedicineUnit.objects.count()
print(f"\n📊 Total MedicineUnits: {total_units}")

# Count total stats
total_stats = MedicineUnitStats.objects.count()
print(f"📊 Total MedicineUnitStats: {total_stats}")

# Find units without stats
units_without_stats = MedicineUnit.objects.filter(stats__isnull=True)
missing_count = units_without_stats.count()
print(f"\n⚠️  MedicineUnits without stats: {missing_count}")

if missing_count > 0:
    print(f"\n🔧 Action needed: Run backfill command")
    print(f"   python3 manage.py backfill_medicine_unit_stats")
else:
    print(f"\n✅ Perfect! All MedicineUnits have stats.")

# Show sample stats
if total_stats > 0:
    print(f"\n📋 Sample stats (first 3):")
    for stat in MedicineUnitStats.objects.all()[:3]:
        print(f"   - Unit ID: {stat.unit.id}, Sold Total: {stat.sold_total}, Views: {stat.view_count}")

print("\n" + "=" * 60)
