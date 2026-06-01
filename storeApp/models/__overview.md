# Store Models — Overview

Tổng quan schema `storeApp`. **Source of truth:** `product.py`, `cart.py`, `order.py`, `voucher.py`. Cập nhật file này khi có migration đổi field/constraint.

- DB alias: `store` (`storeApp/db_router.py`). Mọi model kế thừa `BaseModel` → `created_date`, `updated_date`, `active`.
- Catalog canonical: `Product` / `ProductVariant` / `ProductVariantUnit` (legacy `mainApp.Medicine*` đã drop).
- Import CLI: `manage.py store_catalog import-csv` → `catalog_import/` (orchestration: `store_import_csv.py`). Audit: `store_catalog audit`. Backfill M2M: `backfill_product_categories`.

## Files

| File | Domain |
|------|--------|
| `product.py` | Brand, Category, Product, ProductCategory, Variant, PVU, Batch, Notification, SearchKeyword |
| `cart.py` | Cart, CartItem |
| `order.py` | ShippingMethod, PaymentMethod, Order, OrderItem |
| `voucher.py` | Voucher, VoucherRedemption |

## Product

### Category

- Cây: `parent`, `level`, `path`, `path_slug` (unique). `unique_together (parent, slug)`.
- `save()` auto slug + rebuild descendants.

### Product

| Field | Ghi chú |
|-------|---------|
| `mid` | Unique SKU — khóa upsert import |
| `name`, `slug` | Unique |
| `category` | FK **primary** (canonical URL; sync với M2M sau) |
| `categories` | M2M `through=ProductCategory` — import `assign_category()`; list/detail/search filter theo M2M |
| `content.*` (7) | Detail only; HTML sanitized (scraper) hoặc plain text cũ; FE DOMPurify |
| `ingredients` | Comma-list `"Name: amount, …"` — FE parse riêng |

### ProductCategory (M2M through)

- `product`, `category`, `is_primary`, `sort_order`.
- Unique `(product, category)`; partial unique một `is_primary=True` / product.
- Table: `store_product_category`.

### ProductVariant / PVU / Batch

- **Variant:** `sku` (≈ `mid`), `packing`, `packing_meta`, `in_stock` (cache batch, base unit). `get_category_info()` → primary breadcrumb; serializer thêm `category_slugs[]`, `primary_category_slug`, `listed_under_slug` (list context).
- **PVU:** `unit_name`, `quantity_in_base`, `price_value`, `is_default` (1/variant), unique `(variant, unit_name)`.
- **MedicineBatch:** `remaining_quantity` = nguồn stock thật; `in_stock` = cache.

### Khác

- `ProductVariantStats` 1-1 variant. `Notification` HSD/tồn. `SearchKeyword` + `record_search()`.

## Cart

### Cart

| Field | Ghi chú |
|-------|---------|
| `user_id` | Nullable — user cart |
| `guest_session_id` | UUID — guest cart (`X-Guest-Session`) |
| XOR constraint | Đúng một trong hai khi có owner |
| `status` | `ACTIVE` \| `CHECKED_OUT` \| `ABANDONED` |
| `version` | Optimistic lock API |
| Vouchers / shipping | `order_voucher`, `shipping_voucher`, `shipping_method` |
| `checkout_order` | Partial checkout — cart có thể vẫn `ACTIVE` |

- Unique 1 `ACTIVE` / `user_id` hoặc / `guest_session_id`.
- Guest: `POST /carts/merge-guest/` gộp guest → user khi login (lines còn `ACTIVE`).

### CartItem

- FK `product_variant`, `product_variant_unit` (nullable), `quantity`, `unit_price_snapshot`.
- Unique `(cart, product_variant, product_variant_unit)`.

## Order

- **Order:** `order_number` auto; `user_id` **nullable** (guest checkout); totals + 2 voucher FK; `status` lifecycle.
- **OrderItem:** variant + PVU snapshot, `quantity`, `price`.
- **ShippingMethod / PaymentMethod:** catalog phương thức.

## Voucher

- `scope`: `ORDER_DISCOUNT` \| `SHIPPING_DISCOUNT` — 2 slot tách trên Cart/Order.
- JSON `applicable_products` (mid), `applicable_categories` (slug).
- `validate_for_context(...)`, `VoucherRedemption` cho `per_user_limit`.

## Quan hệ (rút gọn)

```
Category ──< Product ──< ProductVariant ──< ProductVariantUnit
              │              ├── MedicineBatch
              │              └── ProductVariantStats
              └── ProductCategory >── Category   (M2M, schema)

Cart (user_id XOR guest_session_id) ──< CartItem >── ProductVariant / PVU
  └──► Order (user_id nullable) ──< OrderItem
Voucher ──< VoucherRedemption >── Order
```

## Rules khi sửa code

1. **Giá/tồn:** snapshot cart/order theo PVU; stock check = `qty × quantity_in_base` vs batch sum.
2. **Đổi unit trong cart:** conflict unique line; bump `version`; re-snapshot price.
3. **Voucher:** không trộn scope order vs shipping.
4. **Category:** list/detail/search/voucher dùng **ProductCategory M2M**; FK `Product.category` = primary (canonical SEO, sync sau import). List card: **1 row / product** (`variant_listing.one_variant_per_product`).
5. **Guest:** không tạo User khi checkout; `Order.user_id = null`.

## Catalog contract (tóm tắt)

| Layer | Khóa / field quan trọng |
|-------|-------------------------|
| Product | `mid`, `slug`, `category` (primary), `content.*` |
| Variant | `packing`, `in_stock`, `is_published` |
| PVU | `unit_name`, `quantity_in_base`, `price_value`, `is_default` |
| FE card | `product_entity_id`, `variant_count?`, `unit_options[]`, `web_slug`, `category_info` + `listed_under_slug` |
| API list `count` | Distinct **products** (sau dedupe), không đếm từng variant |
| FE routing | `GET /api/store/resolve-path/{path}/` → category \| product \| not_found |

**Product card:** 1 card / 1 Product; href canonical (`web_slug` hoặc primary path); chọn quy cách trên PDP (`?v=`). Add cart = variant id + PVU id.

**Multi-category:** cùng `mid` → thêm `ProductCategory` (không tạo product mới); primary FK giữ khi đã có. URL `/{context_path}/{slug}` hợp lệ nếu path ∈ M2M; canonical = primary `path_slug`.

**Counts:** category `productCount` / pagination `count` = distinct products (`count_distinct_products`). Sidebar facet counts: `[Done] category-facet-distinct-product-count.plan.md` (`Count('product_id', distinct=True)`).

**Audit:** `store_catalog audit --overview` — M2M groups + primary FK vs M2M; `--mid` checklist `category leaf in M2M`, `primary FK = M2M primary`.

## Docs liên quan

- `storeApp/guidelines/cart-first-checkout.md`
- `storeApp/guidelines/dynamic-filters.md`, `search-faceted-api.md`
- `storeApp/services/variant_listing.py`, `store_path_resolver.py`
- `oupharmacy-store/docs/ROUTING.md`
- `PersonalProject/plans/[Done] product-multi-category-m2m.plan.md`
