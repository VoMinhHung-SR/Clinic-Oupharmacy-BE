# Store Models — Overview

Tổng quan **cấu trúc model** của `storeApp`. Tài liệu mục đích để onboard nhanh và làm context cho các plan/feature liên quan tới Product / Cart / Order / Voucher.

> Source of truth: `storeApp/models/{product,cart,order,voucher}.py`. Tài liệu này phải được cập nhật khi schema thay đổi (migration mới ảnh hưởng field/constraint dưới đây).

## 0. Lịch sử & nguồn dữ liệu chính (canonical)

- **Hiện tại (canonical)**: `storeApp.Product` + `storeApp.ProductVariant` + `storeApp.ProductVariantUnit` là **nguồn lưu sản phẩm chính**. Mọi feature mới (cart, order, scraper importer, search…) phải target bộ model này.
- **Legacy đã bị xóa**: `mainApp.Medicine` + `mainApp.MedicineUnit` + `mainApp.MedicineUnitStats` + `mainApp.Category` đã bị `DeleteModel` trong migration `mainApp/0018_drop_medicine_legacy_tables_store_only.py`. Code/tool nào còn import từ `mainApp.models` các class này sẽ **ImportError** ngay khi chạy.
  - Các trans‑mapping cũ giữa `Medicine.mid` ↔ `Product.mid` đảm bảo khóa upsert không đổi.
- **Importer canonical cho CSV scraper**: `storeApp/management/commands/catalog_import/store_import_csv.py` (CLI: `manage.py store_catalog import-csv`). Helper packing: `catalog_import/store_import_packaging.py`. Target `Product`*/`Category` qua DB alias `store`. Các file `storeApp/management/commands/import_csv_data.py` và `storeApp/utils/product_import.py` (legacy) đã **được xóa** vì target model đã không còn tồn tại.
- **Scrape data dirs**: `storeApp/test/data/new/` (có `saleUnits`), `storeApp/test/data/old/` (chủ yếu `packageOptions`). **Giá thiếu/0**: `store_import_pricing.ensure_unit_pricing` — infer từ unit cùng variant → fallback row → smart random theo tier (viên/gói/hộp…) × `quantity_in_base` (mặc định bật; `--no-smart-random-price` = random phẳng). **CLI**: `store_catalog import-refactor` / `import-csv`; batch qty ≈ `quantity_in_base × random(--batch-pack-mult-*)`.
- **Kiểm tra catalog sau import**: `python manage.py store_catalog audit --overview` (thống kê DB) và `--mid <sku> [--scrape-root …]` (so CSV). Schema JSON in `--overview` trùng mục **§9** dưới đây.
- **Trạng thái tham chiếu (sau phase new + old apply)**: ~6936 `Product`, ~6944 `ProductVariant`, ~8377 `ProductVariantUnit`, ~6944 `MedicineBatch`; `Units price <= 0` = 0; `Variants no default unit` = 0. Một vài row scrape trùng `name` khác `mid` có thể skip update `name` (constraint unique) — không ảnh hưởng bulk catalog.
- Khi đụng feature liên quan import / catalog: đọc model `storeApp.Product` trước, không tham chiếu `Medicine` trừ khi đang sửa snapshot code (vd `PrescriptionDetail.item_name_snapshot`).

## 1. Tổ chức file

```
storeApp/models/
├── __init__.py     # re-export tất cả models (from .cart import * ...)
├── product.py      # Product domain (catalog, batch, search)
├── cart.py         # Cart + CartItem
├── order.py        # Order + OrderItem + Shipping/Payment method
└── voucher.py      # Voucher + VoucherRedemption
```

Tất cả model kế thừa `BaseModel` (từ `mainApp.models`) → có sẵn `created_date`, `updated_date`, `active`.

DB routing: model `storeApp` đi qua database alias `store` (xem `storeApp/db_router.py`); các model dùng chung (User, …) ở database `default`.

## 2. Product domain (`product.py`)

### `Brand`

- `name` (unique), `country`, `active`.
- Index: `(country, active)`.
- Table: `store_brand`.

### `Category` — cây phân cấp

- `name`, `slug`, `parent` (self-FK), `level`, `path`, `path_slug` (unique).
- `save()` tự sinh `slug` từ `name`, recompute `level/path/path_slug`, và **rebuild descendants** khi đổi parent/name/slug.
- Helpers: `get_category_array()`, `get_or_create_from_array(...)`.
- Constraint: `unique_together (parent, slug)`.
- Table: `store_category`.

### `Product` — sản phẩm gốc (migrated from Medicine)

- `name` (unique, max 254), `mid` (unique, SKU), `slug` (unique), `web_name`.
- Mô tả y tế (7 field — **chỉ trang chi tiết**, không Product Card): `description`, `ingredients`, `usage`, `dosage`, `adverse_effect`, `careful`, `preservation`.
- Meta legacy trên Product: `origin`, `manufacturer`, `shelf_life`, `specifications` (JSON) — **importer scrape hiện ghi `origin` / `manufacturer` / `shelf_life` vào `ProductVariant.packing_meta`**, không bắt buộc đồng bộ lên Product.
- FK: `brand`, `**category**` (một leaf category — xem §9.3).
- Table: `store_product`.

#### Content fields contract (scraper v1.3.0+)

Các 7 field mô tả ở trên đều là `models.TextField`, **nhưng nội dung chúng chứa khác nhau theo loại field**:


| Field                                                          | Format hiện tại (v1.3.0+)                                                                                                                                                                                                                               | Nguồn                                                                        | Render                                                                   |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `description`                                                  | **sanitized HTML** (`<p>`, `<strong>`, `<em>`, `<ul>/<li>`, `<h2>-<h6>`, `<table>` cho dosage/comparison; KHÔNG có `<a>` (anchor → `<strong>` từ v1.3.4 để giấu URL nguồn), `<img>`, `<script>`, `<iframe>`, `class=`, `style=`, event handlers)        | `strategies/product-content-strategy.js::extract` → tag/attr whitelist       | FE phải DOMPurify trước khi `dangerouslySetInnerHTML`                    |
| `usage`, `dosage`, `adverse_effect`, `careful`, `preservation` | **sanitized HTML** (cùng schema)                                                                                                                                                                                                                        | như trên                                                                     | như trên                                                                 |
| `ingredients`                                                  | **comma-separated string** `"Name1: amount1, Name2: amount2, …"` (popup-aware dialog "Xem bảng thành phần"; rỗng nếu sản phẩm không publish thành phần; hoặc nguyên chuỗi `"N viên chứa: X (Ymg)"` từ spec table khi không có popup) | scraper extract 3 case (popup → inline section table → spec fallback → `""`) | FE parser custom split bằng `,` rồi tách `name:amount` thành table 2 cột |


**Pipeline contract**:

```
DOM (rich)
  ↓ scraper sanitize (whitelist tags/attrs, drop img/script/style/event handlers,
    drop javascript:/data: URLs)
sanitized HTML string  +  ingredients comma-list
  ↓ store_import_csv.py pass-through (no transform)
Product.{description, …} TextField
  ↓ FE DOMPurify (defense-in-depth — re-sanitize at render boundary)
oupharmacy-store/src/components/products/ProductDescriptionSection.tsx
```

**Backward-compat**:

- Rows scraped trước v1.3.0 chứa **plain text** (line breaks `\n`). FE renderer bọc auto vào `<p>...<br/></p>` trong `HtmlContent` để render OK trong cả 2 chế độ.
- Khi re-scrape sản phẩm bằng extension v1.3.0+, các field sẽ tự update sang HTML sanitized — không cần migration thủ công.

**KHÔNG được làm**:

- Inject HTML thẳng từ DB sang client mà không sanitize lại (mất defense-in-depth).
- Lưu HTML chưa qua scraper sanitize (vd nếu mở Django admin edit thủ công, phải dán HTML đã sanitize hoặc viết save-hook để sanitize ở layer model). Hiện tại không có WYSIWYG nên risk thấp; nếu thêm sau, doc lại ở plan riêng.
- Lưu thêm `<img>` vào description vì scraper đang strip toàn bộ ảnh embed (quyết định đã chốt ở `plans/[UnDone] rich-html-product-content.plan.md`); nếu cần ảnh sau này, cần thêm pipeline upload Cloudinary + bật `<img>` trong allow-list cả 2 lớp sanitize.

### `ProductVariant` — SKU bán (1 row API list ≈ 1 card FE)

- FK `product`, `sku` (unique, thường = `product.mid`), `packing`, `packing_meta` (JSON: `origin`, `manufacturer`, `shelf_life`, `units[]`), `image` (Cloudinary), `images` (JSON), `registration_number` (non-import từ scrape).
- `base_unit` (label đơn vị có `min quantity_in_base` trên PVU; cart/stock dùng `quantity_in_base`, không đọc field này trực tiếp), `in_stock` (cache tổng `MedicineBatch.remaining_quantity` theo đơn vị cơ sở).
- Flags: `is_published`, `is_hot`, `product_ranking`.
- Helper: `get_category_info()` (trả về `category`, `categoryPath`, `categorySlug`).
- Index: `(is_published, product_ranking)`, `(is_hot, is_published)`.
- Table: `store_product_variant`.

### `ProductVariantUnit` — đơn vị bán

- FK `variant`, `unit_name` (Hộp / Vỉ / Viên / Gói…), `quantity_in_base` (`>= 1`).
- Pricing: `price_value`, `price_display`, `compare_at_price`.
- Flags: `is_default`, `is_published`, `unit_order`.
- `save()` tự đảm bảo chỉ 1 default/variant.
- Constraints:
  - unique `(variant, unit_name)`.
  - partial unique 1 default/variant (`store_pvu_one_default_per_variant`).
  - check `quantity_in_base >= 1`.

### `ProductVariantStats` — 1-1 với variant

- `sold_total`, `sold_30d`, `sold_7d`, `view_count`, `wishlist_count`, `updated_at`.
- Table: `store_product_variant_stats`.

### `MedicineBatch` — lô thuốc theo variant

- `batch_number` (unique), FK `product_variant`, `import_date`, `expiry_date`.
- `quantity`, `remaining_quantity` (theo base_unit), `import_price_per_base_unit`.
- Properties: `is_expired`, `days_until_expiry`, `is_near_expiry` / `is_near_expiry_within(days)`.
- Index: `(product_variant, expiry_date)`, `(expiry_date, remaining_quantity)`.

### `Notification` — cảnh báo HSD/tồn kho/hỗ trợ

- `notification_type`: `EXPIRY_WARNING | EXPIRY_URGENT | EXPIRED | LOW_STOCK | ADMIN_SUPPORT | OTHERS`.
- FK optional: `product_variant`, `batch`.
- `title`, `message`, `is_read`, `read_at`; helper `mark_as_read()`.

### `SearchKeyword` — từ khóa tìm kiếm phổ biến

- `keyword`, `keyword_lookup` (unique, casefold), `hit_count`, `last_searched_at`.
- `record_search(keyword)` atomic (try update F-expression, fallback create, retry trên `IntegrityError`).
- `normalize_keyword(...)`: NFKC + collapse whitespace.

## 3. Cart domain (`cart.py`)

### `Cart`

- `user_id` (BigInt), `status`: `ACTIVE | CHECKED_OUT | ABANDONED`.
- FK optional: `shipping_method`, `order_voucher`, `shipping_voucher`, `checkout_order` (FK `Order` — phục vụ partial checkout, cart sống tiếp sau khi tạo order từ subset items).
- Tổng tiền: `subtotal`, `shipping_fee`, `discount_amount`, `shipping_discount_amount`, `total`.
- `version` (PositiveInteger) — **optimistic locking** cho mutate API.
- Constraint: unique 1 cart `ACTIVE` / user (`store_cart_one_active_per_user`).
- Index: `(user_id, status)`, `(status, updated_date)`.

### `CartItem`

- FK `cart`, `product_variant`, `**product_variant_unit`** (nullable, đơn vị bán đã chọn).
- `quantity` (>=1), `unit_price_snapshot`.
- Constraint unique `(cart, product_variant, product_variant_unit)` — chú ý conflict khi switch unit sang đơn vị đã có dòng.
- Index: `(cart, updated_date)`, `(product_variant)`.

## 4. Order domain (`order.py`)

### `ShippingMethod` / `PaymentMethod`

- `ShippingMethod`: `name`, `price`, `estimated_days`, `active`.
- `PaymentMethod`: `name`, `code` (unique: `COD/MOMO/VNPAY/...`), `active`.

### `Order`

- `order_number` (unique, auto `ORDYYYYMMDD####` qua `save()` retry tối đa 5 lần khi đụng `IntegrityError`).
- `user_id` (nullable — guest order).
- `shipping_address`, FK `shipping_method` / `payment_method` (PROTECT).
- Tổng tiền: `subtotal`, `shipping_fee`, `discount_amount`, `shipping_discount_amount`, `total`.
- `status`: `PENDING | CONFIRMED | SHIPPING | DELIVERED | CANCELLED`.
- `notes`, FK optional `order_voucher`, `shipping_voucher`.

### `OrderItem`

- FK `order`, `product_variant` (PROTECT), `**product_variant_unit`** (nullable, snapshot đơn vị bán).
- `quantity`, `price` (snapshot theo unit), property `subtotal`.

## 5. Voucher domain (`voucher.py`)

### `Voucher`

- `code` (unique), `type`: `FIXED | PERCENT`.
- `scope`: `ORDER_DISCOUNT | SHIPPING_DISCOUNT` → 2 slot tách bạch trên `Cart`/`Order`.
- `value`, `max_discount`, `min_order_value`.
- `applicable_products` (JSON list of product `mid`), `applicable_categories` (JSON list of category `slug`).
- Window: `start_at`, `end_at`. Limits: `usage_limit`, `per_user_limit`, `used_count`.
- Validation codes (string): `inactive`, `not_started`, `expired`, `usage_limit_reached`, `missing_order_subtotal`, `min_order_not_met`, `product_not_applicable`, `category_not_applicable`, `per_user_limit_reached`, `ok`.
- Methods chính:
  - `is_valid()` — check active + window + usage_limit.
  - `validate_for_context(order_subtotal, product_mids, category_slugs, user_id, current_user_redeem_count, using)` → `(bool, code)`.
  - `calculate_discount(amount)`, `calculate_discount_for_scope(order_subtotal, shipping_fee)` (tự branch theo scope).
  - `increment_used_count(using)` — `select_for_update`, fail-safe revalidate trước khi tăng.

### `VoucherRedemption`

- FK `voucher`, `order`, `user_id`, `scope`, `discount_amount`.
- Index `(voucher, user_id)`, `(order)`, `(user_id, created_date)` — phục vụ `per_user_limit` lookup.

## 6. Quan hệ tổng

```
Brand ─┐
       ▼
Category ──< Product ──< ProductVariant ──< ProductVariantUnit
                                  │             │
                                  ├──< MedicineBatch
                                  ├──< Notification
                                  └──1 ProductVariantStats

Cart 1──< CartItem >── ProductVariant
 │           │
 │           └── product_variant_unit (FK PVU, nullable)
 │
 ├── shipping_method, order_voucher, shipping_voucher
 └── checkout_order ──► Order 1──< OrderItem >── ProductVariant
                                   └── product_variant_unit (FK PVU, nullable)

Voucher 1──< VoucherRedemption >── Order
```

## 7. Lưu ý khi mở rộng

- **Switch packaging trong cart** (plan đang mở `cart-packaging-switch-full-workflow`): trước khi đổi `CartItem.product_variant_unit`, cần (1) kiểm tra unit `is_published` + cùng `variant`, (2) xử lý conflict với constraint unique `(cart, variant, unit)` (merge vs 409), (3) re-snapshot `unit_price_snapshot`, (4) bump `Cart.version`.
- **Pricing snapshot**: `CartItem.unit_price_snapshot` và `OrderItem.price` đều là snapshot theo `ProductVariantUnit.price_value` tại thời điểm thao tác — không lấy lại live khi recalculate trừ khi user thực sự đổi unit/quantity.
- **Voucher 2 slot**: luôn tách `order_voucher` (scope=`ORDER_DISCOUNT`) và `shipping_voucher` (scope=`SHIPPING_DISCOUNT`); không set chéo scope.
- **Stock**: `ProductVariant.in_stock` là cache theo base_unit; nguồn thật là sum `MedicineBatch.remaining_quantity`. Khi tính khả dụng cho đơn vị bán, phải nhân/chia `ProductVariantUnit.quantity_in_base`.
- **Partial checkout**: `Cart.checkout_order` dùng để tham chiếu order vừa tạo từ subset items, cart vẫn `ACTIVE` nếu còn item chưa checkout.

## 8. Liên kết tài liệu khác

- `storeApp/guidelines/cart-first-checkout.md` — flow chuẩn cart-first checkout.
- `storeApp/guidelines/dynamic-filters.md` — filter động cho catalog.
- `storeApp/guidelines/search-faceted-api.md` — faceted search.
- `storeApp/README.md` — overview module và DB routing.

## 9. Contract catalog (post-refactor) — DB, API, FE

Mục này chuẩn hóa **những field cần thiết** sau re-import; `store_audit_product --overview` in cùng shape JSON.

### 9.1 Payload lõi (lookup / import / audit)


| Layer             | Field                          | Nguồn                                      | Ghi chú                                                |
| ----------------- | ------------------------------ | ------------------------------------------ | ------------------------------------------------------ |
| **Product**       | `mid`                          | `basicInfo.sku`                            | Unique; khóa upsert                                    |
|                   | `slug`, `name`, `web_name`     | `basicInfo.*`                              | `name` unique — 2 SKU khác nhau không được cùng `name` |
|                   | `brand`                        | `basicInfo.brand`                          | FK `Brand`                                             |
|                   | `category_slug`                | `category.categorySlug`                    | Leaf path, vd `thuoc/co-xuong-khop/...`                |
|                   | `content.*` (7)                | `content.*`                                | HTML hoặc plain text; detail only                      |
| **Variant**       | `packing`                      | `pricing.packageSize`                      | Hiển thị quy cách trên card                            |
|                   | `sku`                          | thường = `mid`                             |                                                        |
|                   | `packing_meta`                 | `specifications.*` + unit names            | `origin`, `manufacturer`, `shelf_life`                 |
|                   | `base_unit`                    | suy từ PVU                                 | Label; logic giá/tồn = PVU                             |
|                   | `in_stock`                     | cache batch                                | Đơn vị cơ sở (base)                                    |
|                   | `is_published`                 | —                                          | List API filter                                        |
| **PVU** `units[]` | `unit_name`                    | `saleUnits.unitName` hoặc `packageOptions` |                                                        |
|                   | `quantity_in_base`             | `saleUnits.quantityInBase` / heuristic     | ≥ 1                                                    |
|                   | `price_value`, `price_display` | scrape hoặc `ensure_unit_pricing`          | Cart snapshot                                          |
|                   | `is_default`, `unit_order`     | scrape / importer                          | Đúng 1 default / variant                               |
| **Batch**         | `remaining_quantity`           | import synthetic                           | Nguồn thật của `in_stock`                              |


**Scrape sources**: `data/new` → `pricing.saleUnits[]` (ưu tiên). `data/old` → `pricing.packageOptions` (fallback).

### 9.2 Một Product Card (list / grid / search mini)

API: `ProductVariantSerializer` (`storeApp/serializers.py`). FE: `buildProductCardPayload` → `ProductCard.tsx` (`oupharmacy-store`).

**Hiển thị trên card (bắt buộc):**


| UI                | API / payload                                                 | Rule                                                           |
| ----------------- | ------------------------------------------------------------- | -------------------------------------------------------------- |
| Ảnh               | `image_url` ← `variant.image`                                 | Placeholder nếu trống                                          |
| Tên               | `product.web_name` || `product.name`                          |                                                                |
| Giá               | `price_display`, `price_value`                                | Từ **default** `ProductVariantUnit`                            |
| Giá gạch / % giảm | `compare_at_price`, `discount_percent`                        | Optional                                                       |
| Quy cách ngắn     | `packing`                                                     | vd `Hộp 60 Viên`                                               |
| Chọn đơn vị       | `unit_options[]`                                              | Chỉ khi >1 unit; mỗi option: `unit_id`, `unit_name`, `price_*` |
| Link              | `category_info.categorySlug` + `product.slug`                 | URL `/{categorySlug}/{productSlug}`                            |
| CTA giỏ hàng      | `id` = **variant id**; `product_variant_unit_id` = **PVU id** | `add()` cần cả hai; `packaging` gửi `unit_name` đã chọn        |
| Hết hàng          | `in_stock` (base units)                                       | So với qty cart × `quantity_in_base` khi checkout              |


**Không đưa lên card:** 7 field `content.*`, `ingredients` dài, `dosage`, `registration_number`, `packing_meta` chi tiết (detail / accordion).

**Detail page thêm:** full `product` + `content` (DOMPurify), toàn bộ `unit_options`, `packing_meta`, brand, category breadcrumb.

### 9.3 Category — hiện tại vs mong muốn

- **Hiện tại (schema)**: mỗi `Product` có **một** `category` (FK leaf). List/filter/voucher dùng `categorySlug` đó.
- **Nghiệp vụ “một thuốc nhiều danh mục”**: hợp lý (cùng SP có thể thuộc mắt + não), nhưng **chưa implement** (cần M2M hoặc bảng `product_categories` + API). Import nhiều CSV cùng `mid` khác `categorySlug` → **category cuối cùng ghi đè**.
- **Khác với lỗi trùng `name`**: hai `mid` khác nhau (vd WIT vs OTiV) là **hai product**; lỗi import là scrape gán cùng `name` cho SKU khác.

### 9.4 Khớp `models-overview` ↔ overview DB (checklist)


| Kiểm tra                                 | Kỳ vọng sau refactor                            |
| ---------------------------------------- | ----------------------------------------------- |
| Mỗi variant published có ≥1 PVU          | ✓                                               |
| Đúng 1 `is_default` / variant            | ✓ (constraint DB)                               |
| `price_value` > 0 trên units bán         | ✓ (overview: 0 units ≤0)                        |
| `in_stock` vs batch                      | Nên `sync_in_stock_cache` nếu lệch (spot-check) |
| Card API có `unit_options` + giá default | ✓ từ serializer                                 |
| Content HTML                             | Pass-through; FE sanitize lại                   |


Cập nhật mục §9 khi đổi serializer, `ProductCardPayload`, hoặc schema scrape.