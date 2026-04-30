# Dynamic Filters - Guideline

Tài liệu này mô tả **công dụng**, **cách sử dụng**, và **quy tắc kỹ thuật** cho feature dynamic filters của Store.

## 1) Công dụng của feature

Feature `dynamic-filters` dùng để:

- Trả về bộ filter sidebar theo category hiện tại (`brand`, `country`, `priceRange`, ...).
- Trả về `subcategories` để FE điều hướng khi category quá lớn.
- Tối ưu hiệu năng bằng chế độ `overLimit` (không build full filters cho category rất lớn).

Endpoint chính:

- `GET /api/store/dynamic-filters/{category_slug}/`

## 2) Cách FE sử dụng đúng

Luồng chuẩn ở trang category:

1. Gọi listing: `GET /api/store/{category_slug}?page=1&page_size=12...`
2. Gọi filters: `GET /api/store/dynamic-filters/{category_slug}/?include_variants=true&include_counts=true`
3. Render:
  - Nếu `overLimit = false`: render filter sidebar bình thường.
  - Nếu `overLimit = true`: ưu tiên hiển thị `subcategories`, không ép render full filters.

Lưu ý FE:

- Không assume `filters` luôn là array (có thể `null` khi overLimit).
- `subcategories` luôn là nguồn dữ liệu quan trọng cho navigation.

## 3) Cấu trúc backend

- `storeApp/viewsets/dynamic_filters.py`: HTTP layer.
- `storeApp/services/dynamic_filters_service.py`: orchestration + cache + overLimit.
- `storeApp/services/filter_helpers.py`: resolve category/queryset/brand/subcategories.
- `storeApp/services/filter_extractors.py`: extract variants từ dữ liệu sản phẩm.
- `storeApp/services/filter_builders.py`: build options + count cho từng filter.

## 4) Rule bắt buộc (để tránh lỗi 500)

### 4.1 DB alias

Phải query đúng DB chứa bảng `store_`*:

- Ưu tiên alias `store` nếu tồn tại trong `settings.DATABASES`
- fallback `default` khi single-db environment

Tuyệt đối tránh hard-code `.using("default")` cho dynamic filters khi môi trường đang tách `store`.

### 4.2 Schema mới

Code dynamic filters đã chuyển từ legacy sang schema mới:

- `medicine` -> `product`
- `medicine__brand_id` -> `product__brand_id`
- `select_related("medicine")` -> `select_related("product")`

Không dùng lại token legacy trong feature này.

### 4.3 Giá sản phẩm cho filter

`ProductVariant` không lưu cột vật lý `price_value`.

Khi cần lọc/sort theo giá, queryset phải được annotate:

1. `ProductVariantUnit.is_default=True, is_published=True`
2. fallback published unit đầu tiên theo `unit_order, id`
3. fallback `0`

## 5) Query params & response

### Query params

- `use_cache=true|false` (default `true`)
- `include_variants=true|false` (default `true`)
- `include_counts=true|false` (default `true`)

### Response fields chính

- `categorySlug`, `categoryName`
- `productCount`
- `hasSubcategories`, `subcategories`
- `filters`
- `variants` (nếu `include_variants=true`)
- `overLimit`

## 6) Note migration (mainApp -> storeApp)

Feature này trước đây dùng mô hình clinic:

- `mainApp.Medicine`, `mainApp.MedicineUnit`

Hiện tại đã migrate hoàn toàn sang store schema:

- `storeApp.Product`, `storeApp.ProductVariant`, `storeApp.ProductVariantUnit`

Khi review PR liên quan dynamic filters, cần kiểm tra:

- Không còn `.medicine`, `medicine__...`, `select_related("medicine")`
- Không còn assumption field `package_size` trên `ProductVariant` (dùng `packing`)

## 7) Checklist verify nhanh

1. `python3 manage.py check`
2. Test root category:
  - `/api/store/dynamic-filters/thuoc/?include_variants=true&include_counts=true`
3. Test nested category:
  - `/api/store/dynamic-filters/duoc-my-pham/cham-soc-co-the/?include_variants=true&include_counts=true`
4. Test listing cùng slug:
  - `/api/store/duoc-my-pham/cham-soc-co-the?page=1&page_size=12`
5. Confirm không có lỗi:
  - `relation "store_category" does not exist`
  - `Invalid field name ... select_related: 'medicine'`

## 8) Related guidelines

- Cart-first checkout flow: `storeApp/guidelines/cart-first-checkout.md`
- Search APIs + facets: `storeApp/guidelines/search-faceted-api.md`