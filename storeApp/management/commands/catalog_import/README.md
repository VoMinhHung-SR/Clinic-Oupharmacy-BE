# catalog_import

Logic import/audit catalog (DB alias `store`). CLI entry: `../store_catalog.py`.

```bash
python manage.py store_catalog import-csv [path] [--dry-run] ...
python manage.py store_catalog import-refactor [--apply] ...
python manage.py store_catalog audit --overview
python manage.py backfill_product_categories [--dry-run]
```

## Module layout

| File | Vai trò |
|------|---------|
| `store_import_csv.py` | CLI orchestration (đọc file, loop rows, stats) |
| `store_import_row.py` | Parse row: JSON flatten, brand/country, batch helpers, saleUnits payload |
| `store_import_categories.py` | `category.category[]` → leaf `Category` (cache) |
| `store_import_products.py` | Brand + Product upsert; **ProductCategory merge** |
| `store_import_variants.py` | Variant, PVU, MedicineBatch |
| `store_import_packaging.py` | packageOptions → variant payloads |
| `store_import_pricing.py` | Giá synthetic khi thiếu |
| `store_import_refactor.py` | Workflow old/new; gọi `run_import_csv()` |
| `store_audit_product.py` | So DB vs CSV |
| `run.py` | `run_import_csv()` — gọi nội bộ |

## Multi-category import rules

| Rule | Hành vi |
|------|---------|
| Upsert key | `Product.mid` → `slug` → `name` |
| Cùng `mid`, CSV khác category path | `Product.assign_category()` — **không** xóa category cũ |
| Primary | Giữ primary hiện có; chỉ gán primary nếu product chưa có category |
| `Product.category` FK | Luôn = primary sau `assign_category` |

## Scraper field map (tóm tắt)

- `basicInfo.sku` → `Product.mid`, optional `ProductVariant.sku`
- `category.category` → leaf category + M2M
- `pricing.saleUnits[]` (ưu tiên) / `pricing.packageOptions` → PVU
- `content.*` (7 fields) → Product text fields
- `specifications.registrationNumber` — **SKIP**
