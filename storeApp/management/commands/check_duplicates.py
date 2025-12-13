"""
Management command để check duplicates trong database
Chạy: python manage.py check_duplicates [--cleanup]
"""
from django.core.management.base import BaseCommand
from django.db.models import Count
from mainApp.models import Medicine, MedicineUnit


class Command(BaseCommand):
    help = 'Check for duplicate MedicineUnits (same medicine + category)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Remove duplicate MedicineUnits (keeps the first one)',
        )

    def handle(self, *args, **options):
        self.stdout.write('🔍 Checking for duplicates...\n')
        
        # Check MedicineUnits với cùng medicine + category
        duplicates = MedicineUnit.objects.values('medicine', 'category').annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        if duplicates.exists():
            self.stdout.write(self.style.WARNING(f'⚠️  Found {duplicates.count()} duplicate MedicineUnit combinations:'))
            total_duplicates = 0
            for dup in duplicates:
                med = Medicine.objects.get(id=dup['medicine'])
                units = MedicineUnit.objects.filter(
                    medicine_id=dup['medicine'],
                    category_id=dup['category']
                )
                cat_name = 'None' if not dup['category'] else units.first().category.name if units.exists() else 'None'
                self.stdout.write(f'  • Medicine: {med.name[:50]}... | Category: {cat_name} | Count: {dup["count"]}')
                total_duplicates += dup['count'] - 1  # Số lượng cần xóa (giữ lại 1)
            
            if options['cleanup']:
                self.stdout.write(f'\n🧹 Cleaning up {total_duplicates} duplicate MedicineUnits...')
                deleted_count = 0
                for dup in duplicates:
                    units = MedicineUnit.objects.filter(
                        medicine_id=dup['medicine'],
                        category_id=dup['category']
                    ).order_by('id')
                    # Giữ lại unit đầu tiên, xóa các unit còn lại
                    to_delete = units[1:]
                    for unit in to_delete:
                        unit.delete()
                        deleted_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Deleted {deleted_count} duplicate MedicineUnits'))
            else:
                self.stdout.write(f'\n💡 Run with --cleanup to remove {total_duplicates} duplicate MedicineUnits')
        else:
            self.stdout.write(self.style.SUCCESS('✅ No duplicate MedicineUnits found!'))
        
        # Check Medicines với nhiều MedicineUnits (có thể là do category khác nhau - OK)
        meds_with_multiple_units = Medicine.objects.annotate(
            unit_count=Count('units')
        ).filter(unit_count__gt=1)
        
        self.stdout.write(f'\n📊 Medicines with multiple units: {meds_with_multiple_units.count()}')
        if meds_with_multiple_units.exists():
            self.stdout.write('  (This is OK - same medicine can have different categories)')
            for med in meds_with_multiple_units[:5]:
                units = med.units.all()
                categories = [u.category.name if u.category else 'None' for u in units]
                unique_categories = list(set(categories))
                self.stdout.write(f'  • {med.name[:50]}...: {med.units.count()} units')
                self.stdout.write(f'    Categories: {", ".join(unique_categories)}')

