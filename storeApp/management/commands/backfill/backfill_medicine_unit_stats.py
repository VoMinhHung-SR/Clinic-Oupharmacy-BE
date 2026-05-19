"""
Management command to backfill MedicineUnitStats for existing MedicineUnits
Chạy: python manage.py store_backfill medicine-unit-stats
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from mainApp.models import MedicineUnit, MedicineUnitStats


class Command(BaseCommand):
    help = 'Backfill MedicineUnitStats for existing MedicineUnits without stats'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without saving to database'
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No data will be saved'))
        
        self.stdout.write(self.style.SUCCESS('🚀 Starting backfill process...'))
        
        # Get all MedicineUnits
        total_units = MedicineUnit.objects.count()
        self.stdout.write(f'📊 Total MedicineUnits: {total_units}')
        
        # Get MedicineUnits without stats
        units_without_stats = MedicineUnit.objects.filter(stats__isnull=True)
        missing_count = units_without_stats.count()
        
        self.stdout.write(f'⚠️  MedicineUnits without stats: {missing_count}')
        
        if missing_count == 0:
            self.stdout.write(self.style.SUCCESS('✅ All MedicineUnits already have stats!'))
            return
        
        # Create stats for units without stats
        created_count = 0
        errors = []
        
        for idx, unit in enumerate(units_without_stats, 1):
            try:
                if not dry_run:
                    MedicineUnitStats.objects.get_or_create(unit=unit)
                created_count += 1
                
                if idx % 100 == 0:
                    self.stdout.write(f'  ✓ Progress: {idx}/{missing_count} stats created')
            except Exception as e:
                error_msg = f'Unit ID {unit.id}: {str(e)}'
                errors.append(error_msg)
                if len(errors) <= 5:
                    self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
        
        # Final Summary
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS('✅ BACKFILL COMPLETED!'))
        self.stdout.write(f'  📦 Stats created: {created_count}')
        
        if errors:
            self.stdout.write(self.style.ERROR(f'  ❌ Errors: {len(errors)}'))
            for error in errors[:10]:
                self.stdout.write(self.style.ERROR(f'    • {error}'))
        
        # Verify
        if not dry_run:
            remaining = MedicineUnit.objects.filter(stats__isnull=True).count()
            self.stdout.write(f'\n📊 Verification:')
            self.stdout.write(f'  - Total MedicineUnits: {MedicineUnit.objects.count()}')
            self.stdout.write(f'  - Total MedicineUnitStats: {MedicineUnitStats.objects.count()}')
            self.stdout.write(f'  - MedicineUnits without stats: {remaining}')
            
            if remaining == 0:
                self.stdout.write(self.style.SUCCESS('  ✅ Perfect! All units have stats.'))
            else:
                self.stdout.write(self.style.WARNING(f'  ⚠️  Still {remaining} units without stats'))
