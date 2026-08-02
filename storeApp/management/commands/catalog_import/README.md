# catalog_import

Logic import/audit catalog (DB alias `store`). CLI entry: `../store_catalog.py`.

```bash
python manage.py store_catalog import-csv [path] [--dry-run] [--update-existing] ...
python manage.py store_catalog import-refactor [--apply] [--phase old|new|both] ...
python manage.py store_catalog audit --overview [--overview-id-limit 10]
python manage.py backfill_product_categories [--dry-run]
```

## Import catalog (local) — SoT = ``storeApp/test/data/new``

Catalog CSV (đã merge từ `old/` + chỉnh giá / attributes) nằm dưới:

```text
storeApp/test/data/new/<l0>/scraped-data-*.csv
  cham-soc-ca-nhan/
  duoc-mi-pham/
  thiet-bi-y-te/
  thuc-pham-chuc-nang/
  thuoc/
```

Thư mục `storeApp/test/` (CSV + artifacts) **không commit** lên GitHub.

```bash
# Seed filter dictionary first
python manage.py seed_catalog_attributes

# Dry-run toàn bộ data/new
python manage.py store_catalog import-refactor --dry-run --update-existing

# Apply to local store DB
python manage.py store_catalog import-refactor --apply --update-existing
```

Defaults on import:
- **Skip** scrape-error L0 (`cloudflare.com` / `5xx-error-landing`)
- **Dual price model** for `CONSULT` / clinic-ref fills:
  - storefront `price_display` = `CONSULT` (FE “Liên hệ”)
  - clinic kê toa uses numeric `price_value` (sibling infer / smart random / `manual_ref`)
- **Artifact** `storeApp/test/data/artifacts/current/` (see `SUMMARY.md`)
  - `no_price_products.csv`, `by_l0/`, `p3_thuoc_batches/batch_NNN.csv` (100 SKU/lô)
  - Stale copies live under `artifacts/_archive_*/` — do not mix
- **Annotate** source CSV column `import.scrapePriceGap` = `consult|zero|missing`
- Rows with `import.scrapePriceGap=consult`, `pricing.priceDisplay=CONSULT`, or
  `import.priceSource` starting with `manual_ref` force storefront CONSULT after pricing

Re-split an existing aggregate file:

```bash
python -c "from storeApp.management.commands.catalog_import.store_import_artifacts import split_existing_artifact_csv; print(split_existing_artifact_csv('storeApp/test/data/artifacts/no_price_products_local.csv'))"
```

Opt out: `--no-skip-scrape-errors`, `--no-report-no-price`, `--no-annotate-source-csv`.

## Module layout

| File | Vai trò |
|------|---------|
| `store_import_csv.py` | CLI orchestration (đọc file, loop rows, stats) |
| `store_import_row.py` | Parse row: JSON flatten, brand/country, batch helpers, saleUnits payload |
| `store_import_categories.py` | `category.category[]` → leaf `Category` (cache) |
| `store_import_products.py` | Brand + Product upsert; **ProductCategory merge** |
| `store_import_attributes.py` | Product filter attrs → `ProductAttributeValue` (see `guidelines/catalog-attributes.md`) |
| `store_import_variants.py` | Variant, PVU, MedicineBatch |
| `store_import_packaging.py` | packageOptions → variant payloads |
| `store_import_pricing.py` | Giá synthetic khi thiếu; dual CONSULT display + clinic `price_value`; classify `consult`/`zero`/`missing` |
| `store_import_skip.py` | Skip Cloudflare / 5xx-error-landing L0 |
| `store_import_artifacts.py` | Artifact no-price + annotate `import.scrapePriceGap` trên CSV nguồn |
| `store_import_refactor.py` | Workflow import `data/new` (legacy `--phase old` nếu còn) |
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
- **Filter attrs (preferred):**

```json
"attributes": {
  "objectUse": ["Người lớn"],
  "skin": ["Da khô"],
  "flavor": ["Vị Cam"],
  "indications": ["Mụn"],
  "dosageForm": "Gel",
  "brandOrigin": "Pháp"
}
```

  → `ProductAttributeValue` via `store_import_attributes` + `catalog_attribute_map`  
  Flat PDP fields (`objectUse`, `skin`, …) cũng được chấp nhận.
- `specifications.registrationNumber` — **SKIP**
- `manufactor` / country — **not** catalog-attr; use `Brand.country` / `packing_meta.origin`

Chi tiết model/feature: `storeApp/guidelines/catalog-attributes.md`.  
Map mã nguồn: `storeApp/services/catalog_attribute_map.py`.
