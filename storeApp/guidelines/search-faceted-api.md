# Store Search APIs (v1)

Tài liệu này mô tả bộ API search hiện tại cho storefront, gồm analytics keyword, suggest dropdown, và search kết quả đầy đủ có facets.

## 1) API map

### `POST /api/store/search-terms/`

- Ghi nhận một lần người dùng tìm kiếm.
- Chuẩn hóa keyword trước khi lưu (`keyword`, `keyword_lookup`) để dedupe case-insensitive.
- Nếu keyword đã tồn tại, tăng `hit_count` và cập nhật `last_searched_at`.

### `GET /api/store/search-terms/?limit=20`

- Trả danh sách từ khóa phổ biến theo `hit_count`.
- Dùng cho khối "hot search" hoặc analytics nội bộ.

### `GET /api/store/search/suggest/?q=<keyword>`

- Dùng cho typeahead/dropdown khi user đang gõ.
- Trả 4 nhóm:
  - `history_search`
  - `hot_search`
  - `categories`
  - `top_products` (giới hạn mặc định 5)
- Có `meta` (`took_ms`, `source`, `has_more`).

### `GET /api/store/search/?q=<keyword>&page=1&page_size=12&...`

- API trang kết quả search chính.
- Trả:
  - `items`: danh sách product variants
  - `facets`: `category`, `brand`, `price_ranges`, `in_stock`
  - `meta`: `total`, `page`, `page_size`, `has_more`, `took_ms`, `applied_filters`

## 2) Query params cho `/api/store/search/`

- `q`: từ khóa (optional)
- `page`: mặc định `1`
- `page_size`: mặc định `12`, max `100`
- `category`: category id
- `brand`: brand id
- `price_range`: `under_100k` | `100k_300k` | `300k_500k` | `over_500k`
- `in_stock`: `true` | `false`
- `sort`: `relevance` | `price_asc` | `price_desc` | `popular`

## 3) Ranking (v1)

`sort=relevance` dùng thứ tự:

1. `relevance_score` (exact/prefix/contains trên tên sản phẩm và web name; match category/brand có trọng số thấp hơn)
2. `product_ranking`
3. `in_stock`
4. `id` (đảm bảo stable ordering)

## 4) Facets notes

- Facets được tính trên tập kết quả sau khi áp dụng query + filters hiện tại.
- `price_ranges` và `in_stock` dùng aggregate count theo bucket.
- `category` và `brand` trả key + count để FE render filter list.

## 5) FE integration flow

1. User đang gõ ở search box -> gọi `GET /search/suggest`.
2. User submit search / vào trang kết quả -> gọi `GET /search`.
3. User click facet/sort/pagination -> gọi lại `GET /search` với params mới.
4. Sau khi user submit keyword -> gọi `POST /search-terms` để ghi nhận analytics.

## 6) Smoke test checklist

### Basic

- `GET /api/store/search/?q=cảm cúm&page=1&page_size=12` -> HTTP 200, có `items/facets/meta`.
- `GET /api/store/search/?q=&sort=relevance` -> HTTP 200, không lỗi server.

### Filters

- `category` + `brand` kết hợp vẫn trả `meta.applied_filters` chính xác.
- `price_range=under_100k` chỉ trả item trong bucket tương ứng.
- `in_stock=true` chỉ trả item có tồn kho > 0.

### Suggest

- `GET /api/store/search/suggest/?q=cảm cúm` có đủ 4 nhóm dữ liệu.
- `top_products` không vượt quá 5.

## 7) Benchmark checklist (Phase D)

### Command

- `python manage.py benchmark_store_search --iterations 20 --query "cảm cúm" --page-size 12 --sort relevance`

### Metrics cần ghi nhận

- Status code distribution (mong đợi toàn bộ `200`).
- Latency: min, median, mean, p95, max (ms).
- SQL queries per request: min/mean/max.

### Target khuyến nghị cho rollout

- p95 dưới ngưỡng team thống nhất (ví dụ <= 300ms ở local data gần production).
- SQL queries/request ổn định, không tăng bất thường theo pagination cơ bản.

### Latest run (Apr 17, 2026)

- Command: `python manage.py benchmark_store_search --iterations 20 --query "cảm cúm" --page-size 12 --sort relevance`
- Status codes: `{200: 20}`
- Latency (ms): `min 210.89`, `median 238.96`, `mean 259.69`, `p95 361.66`, `max 449.26`
- SQL queries/request: `30` (min=mean=max=30 sau tối ưu prefetch units)