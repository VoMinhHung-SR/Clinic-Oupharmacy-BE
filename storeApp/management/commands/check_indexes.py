"""
Management command để check indexes
Chạy: python manage.py check_indexes
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Check if all required indexes are created'

    def handle(self, *args, **options):
        cursor = connection.cursor()
        
        # Expected indexes
        expected_indexes = {
            'mainapp_medicineunit': [
                'mainapp_med_is_publ_004408_idx',  # is_published, product_ranking
                'mainapp_med_categor_86ae14_idx',  # category, is_published
                'mainapp_med_price_v_97061f_idx',  # price_value, is_published
                'mainapp_med_medicin_07519b_idx',  # medicine, is_published
            ],
            'mainapp_medicine': [
                'mainapp_med_mid_74931e_idx',      # mid
                'mainapp_med_slug_e40b4b_idx',     # slug
                'mainapp_med_brand_i_b724cd_idx',  # brand_id
                'mainapp_med_name_0ccb4a_idx',     # name
            ],
            'mainapp_category': [
                'mainApp_cat_slug_9f1a69_idx',     # slug
                'mainApp_cat_parent__9ebd71_idx',  # parent, level
                'mainApp_cat_path_sl_9f7d33_idx',  # path_slug
            ],
        }
        
        all_good = True
        
        for table, indexes in expected_indexes.items():
            cursor.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = %s
                ORDER BY indexname;
            """, [table])
            
            existing_indexes = {row[0]: row[1] for row in cursor.fetchall()}
            
            self.stdout.write(f'\n📋 {table}:')
            self.stdout.write(f'  Existing indexes: {len(existing_indexes)}')
            
            # Show all existing indexes
            if existing_indexes:
                for idx_name, idx_def in existing_indexes.items():
                    self.stdout.write(f'    • {idx_name}')
            
            # Check expected indexes
            for idx in indexes:
                if idx in existing_indexes:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ {idx}'))
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ {idx} - MISSING!'))
                    all_good = False
        
        if all_good:
            self.stdout.write(self.style.SUCCESS('\n✅ All indexes are present!'))
        else:
            self.stdout.write(self.style.ERROR('\n❌ Some indexes are missing!'))
            self.stdout.write('Run: python manage.py migrate')

