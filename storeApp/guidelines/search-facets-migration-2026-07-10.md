# Migration — Gộp facets vào `/search/`, xóa `dynamic-filters`

**Ngày:** 2026-07-10  
**Phạm vi:** `Clinic-Oupharmacy-BE` (breaking) + `oupharmacy-store` (cleanup FE)  
**Trạng thái:** Code local — **chưa** merge `dev` / **chưa** rebuild Docker tại thời điểm ghi doc

---

## 1. Tóm tắt thay đổi

| Trước | Sau |
|-------|-----|
| Category browse: `resolve-path` + `/search/` + (legacy) `/dynamic-filters/` | Chỉ `resolve-path` + `/search/?category=` |
| Facets sidebar từ API riêng hoặc dead code FE | Facets từ field `facets` trong response `/search/` |
| `dynamic_filters_service` + Python iterator text facets | **`SearchFacetsService`** — SQL aggregate + cache |
| `GET /api/store/dynamic-filters/{slug}/` | **Đã xóa** (404) |

**Lý do:** Store P1 đã search-first; `dynamic-filters` không còn được FE gọi nhưng vẫn tốn maintain + benchmark p95 nhầm path. Gộp SoT facet vào `/search/` đúng luồng user đang dùng.

---

## 2. API map (sau migration)

### Category browse (oupharmacy-store)

```
GET /api/store/resolve-path/{category_path}/
  → category_id, product_count, over_limit, subcategories, ...

GET /api/store/search/?category={id}&brand=&price_range=&in_stock=&sort=&page=
  → items[] + facets{ brand, price_ranges, in_stock } + meta
```

Khi `over_limit: true` → FE **không** gọi `/search/` (chỉ subcategory nav).

### Global search

```
GET /api/store/search/?q={keyword}&page=&sort=
  → items + facets (category buckets khi không có filter category)

Header suggest (nhẹ):
GET /api/store/search/?q=...&page_size=8&include_facets=false
```

### Không còn tồn tại

```
GET /api/store/dynamic-filters/{slug}/   ← REMOVED
```

---

## 3. Query params mới — `GET /search/`

| Param | Default | Mô tả |
|-------|---------|--------|
| `include_facets` | `true` | `false` = bỏ facet SQL (dropdown suggest, items-only) |
| `use_facet_cache` | `true` | `false` = force rebuild facets (debug/benchmark) |

Các param cũ giữ nguyên: `q`, `category`, `brand`, `price_range`, `in_stock`, `sort`, `page`, `page_size`.

Chi tiết: [`search-faceted-api.md`](search-faceted-api.md)

---

## 4. Backend — file / service

### Thêm

| File | Vai trò |
|------|---------|
| `storeApp/services/search_facets_service.py` | Facet SQL, distinct product counts, versioned cache |
| `storeApp/services/catalog_constants.py` | `LARGE_CATEGORY_THRESHOLD` |
| `storeApp/tests/test_search_facets.py` | Facet + cache + search API tests |

### Xóa

| File |
|------|
| `storeApp/viewsets/dynamic_filters.py` |
| `storeApp/services/dynamic_filters_service.py` |
| `storeApp/services/filter_extractors.py` |
| `storeApp/services/filter_builders.py` |
| `storeApp/services/facet_sql_aggregator.py` |
| `storeApp/services/filter_constants.py` |
| `storeApp/guidelines/dynamic-filters.md` |
| `storeApp/tests/test_facet_sql_cache.py` |
| `storeApp/tests/test_filter_facet_distinct_product_count.py` |

### Giữ (rút gọn)

| File | Ghi chú |
|------|---------|
| `storeApp/services/filter_helpers.py` | Chỉ `get_immediate_subcategories()` cho resolve-path |
| `storeApp/views.py` | `search_products`: facets trước sort; prefetch sau facets |

### Cache

- Prefix: `store_search_facets:v{N}:{hash}`
- Bust: `SearchFacetsService.invalidate_all_cache()` — hook sau `store_catalog import-csv` (non dry-run)
- Cache key theo filter state (`q`, `category`, `brand`, `price_range`, `in_stock`) — **không** theo `page`/`sort`

### Facet semantics

- **Brand:** `Count('product_id', distinct=True)` — 1 product nhiều variant vẫn count = 1
- **Category facet:** bỏ qua khi request đã có `category=` (browse sidebar)
- **Price / in_stock:** single aggregate query (buckets)

---

## 5. Frontend store — cleanup

### Xóa

- `src/lib/services/dynamicFilters.ts`
- `src/lib/hooks/useDynamicFilters.ts`
- `src/components/catalog/_shared/filters/DynamicFiltersSidebar.tsx`

### Đổi tên

| Cũ | Mới |
|----|-----|
| `DynamicFiltersSidebar` | `SearchFacetsSidebar` |
| `dynamicFilters` (hook state) | `categoryFacets` |
| `dynamicFilters` (props) | `facetFilters` |
| `DynamicFiltersResponse` | `CategoryBrowseMeta` (alias deprecated giữ tạm) |

### Luồng dữ liệu

`useStorePage` → `useStoreSearch` → `mapSearchFacetsToFilterGroups(facets)` → `SearchFacetsSidebar`

Header: `useHeaderSearchDropdown` → `/search?include_facets=false`

---

## 6. Deploy / rebuild (bắt buộc)

Docker **không mount source** — image cũ vẫn có `dynamic-filters` cho đến khi rebuild:

```bash
cd Clinic-Oupharmacy-BE
docker compose build backend
docker compose up -d backend
```

Store FE (nếu dev đang chạy): restart `npm run dev` hoặc rebuild.

**Không** cần migration DB schema.

---

## 7. Smoke checklist (sau rebuild)

### BE

```bash
# 404 — endpoint cũ đã xóa
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/api/store/dynamic-filters/thuoc/

# 200 — browse + facets
curl -s "http://localhost:8000/api/store/search/?category=6&in_stock=true" | jq '.facets.brand | length'

# suggest nhẹ
curl -s "http://localhost:8000/api/store/search/?q=para&page_size=8&include_facets=false" | jq '.facets'

# over_limit meta
curl -s http://localhost:8000/api/store/resolve-path/thuoc/ | jq '.over_limit, .product_count'
```

Kỳ vọng: dynamic-filters → **404**; search facets → có brand/price; `include_facets=false` → `facets: {}`; `thuoc/` → `over_limit: true`.

### FE (manual)

- [ ] Trang category nhỏ: sidebar brand + giá + còn hàng
- [ ] Filter brand/giá → Network chỉ `/search/` (không `dynamic-filters`)
- [ ] `thuoc/`: over-limit UI, không full listing
- [ ] Header gõ từ khóa: suggest hiện sản phẩm
- [ ] `/tim-kiem?q=...`: kết quả + pagination

### Tests

```bash
docker exec <backend> python manage.py test storeApp.tests.test_search_facets \
  --settings=OUPharmacyManagementApp.settings_test
```

---

## 8. Breaking change — consumers

| Consumer | Ảnh hưởng |
|----------|-----------|
| `oupharmacy-store` | ✅ Đã cleanup — chỉ `/search/` |
| `Clinic-Oupharmacy-FE` (kê toa) | ✅ Không dùng `dynamic-filters` |
| Script/QA gọi tay `dynamic-filters` | ❌ Chuyển sang `/search/?category=` |
| Postman collection cũ | Cập nhật URL |

---

## 9. Performance (tham chiếu Docker staging 2026-07-09)

| Path | Ghi chú |
|------|---------|
| `/search/?category=6` + filters | p95 ~700ms trước optimize prefetch (đo trước migration doc) |
| Facet cache warm | Sub-ms cho cached facet snapshot |
| `include_facets=false` | Bỏ facet SQL cho suggest |

Target tiếp: p95 browse < 400ms (có thể cần thêm item-query optimize, không quay lại `dynamic-filters`).

---

## 10. Related docs

- SoT API: [`search-faceted-api.md`](search-faceted-api.md)
- Store routing: `oupharmacy-store/docs/ROUTING.md`
- Program plan: `PersonalProject/plans/[UnDone] clinic-store-phase-next-roadmap.plan.md`
