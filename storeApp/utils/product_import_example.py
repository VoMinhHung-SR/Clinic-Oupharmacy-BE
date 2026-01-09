"""
Example usage của product import utilities

Chạy:
    python manage.py shell
    >>> from storeApp.utils.product_import import import_csv_file, dry_run_import, print_import_statistics
    >>> stats = import_csv_file('path/to/file.csv', skip_image_upload=True)
    >>> print_import_statistics(stats)
"""
from storeApp.utils.product_import import (
    import_csv_file,
    dry_run_import,
    export_dry_run_to_json,
    print_import_statistics
)


# Example usage:
if __name__ == '__main__':
    csv_file = 'storeApp/test/data/new/thuoc/scraped-data-thuoc-tim-mach-va-mau-501-532.csv'
    
    # Example 1: Dry-run để xem statistics
    print('Example 1: Dry-run import')
    stats = dry_run_import(csv_file, update_existing=True)
    print_import_statistics(stats, csv_file)
    
    # Example 2: Export dry-run to JSON
    print('\nExample 2: Export dry-run to JSON')
    count = export_dry_run_to_json(csv_file, 'demo.json', max_rows=None)
    print(f'✅ Exported {count} rows to demo.json')
    
    # Example 3: Real import (uncomment to use)
    # print('\nExample 3: Real import')
    # stats = import_csv_file(csv_file, skip_image_upload=True, update_existing=False, dry_run=False)
    # print_import_statistics(stats, csv_file)
