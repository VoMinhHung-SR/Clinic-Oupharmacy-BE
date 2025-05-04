import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OUPharmacyManagementApp.settings')
os.environ['FIREBASE_SKIP_INIT'] = '1'

import django
django.setup()

from django.db import connection

def reset_sequences():
    cursor = connection.cursor()
    
    # Get all tables from the database
    cursor.execute("""
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public'
    """)
    tables = cursor.fetchall()
    
    for (table_name,) in tables:
        try:
            # Kiểm tra cột id với đúng tên bảng (không chuyển về chữ thường)
            cursor.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'id' AND table_schema = 'public'
            """, [table_name])
            has_id = cursor.fetchone() is not None
            
            if has_id:
                # Get the current max id (giữ nguyên tên bảng)
                cursor.execute(f'SELECT MAX(id) FROM "{table_name}"')
                max_id = cursor.fetchone()[0] or 0
                
                # Reset the sequence (giữ nguyên tên bảng)
                cursor.execute(f"SELECT setval(pg_get_serial_sequence('\"{table_name}\"', 'id'), {max_id + 1}, false)")
                print(f"Reset sequence for {table_name} to {max_id + 1}")
            else:
                print(f"Table {table_name} does not have an id column")
        except Exception as e:
            print(f"Error resetting sequence for {table_name}: {str(e)}")

if __name__ == "__main__":
    reset_sequences()