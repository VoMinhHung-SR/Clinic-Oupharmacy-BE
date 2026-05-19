# catalog_import

Logic import/audit catalog (DB alias `store`). CLI entry: `../store_catalog.py`.

```bash
python manage.py store_catalog import-csv [path] [--dry-run] ...
python manage.py store_catalog import-refactor [--apply] ...
python manage.py store_catalog audit --overview
```

| File | Vai trò |
|------|---------|
| `store_import_csv.py` | Import CSV/JSON scrape → Product*, variants, units |
| `store_import_refactor.py` | Workflow old/new; gọi `run_import_csv()` |
| `store_audit_product.py` | So DB vs CSV |
| `store_import_packaging.py` | Parse packageOptions / saleUnits (helper) |
| `store_import_pricing.py` | Giá synthetic khi thiếu (helper) |
| `run.py` | `run_import_csv()` — gọi nội bộ, không qua CLI |
