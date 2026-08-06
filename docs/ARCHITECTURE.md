# Architecture — Clinic-Oupharmacy-BE

## Tổng quan

Backend **Django** phục vụ REST API: **mainApp** (clinic, user, examination, thuốc, …) và **storeApp** (API cửa hàng dưới prefix `api/store/`). Entry URL gốc: `OUPharmacyManagementApp/urls.py` → include `mainApp.urls`.

## Luồng request (điển hình)

```mermaid
flowchart LR
  Client --> DjangoURLs
  DjangoURLs --> MainRouter["mainApp router + urlpatterns"]
  MainRouter --> DRFViewsets
  MainRouter --> StoreInclude["path api/store/ → storeApp"]
  StoreInclude --> StoreViews
  DRFViewsets --> ORM["Django ORM / PostgreSQL"]
  StoreViews --> ORM
```



- **DRF `DefaultRouter`** trong `mainApp/urls.py` đăng ký viewsets (`users`, `medicines`, `examinations`, …).
- **OAuth2 / social:** `oauth2_provider`, `oauth2-info/`, `auth/firebase/`, v.v. (chi tiết trong `mainApp/urls.py`).
- **Store:** `path('api/store/', include('storeApp.urls'))` — tách domain storefront khỏi API clinic core.

## Ranh giới


| Prefix / khu             | Gợi ý khi mở rộng                                      |
| ------------------------ | ------------------------------------------------------ |
| `/` (root) qua `mainApp` | API nội bộ clinic, user, lịch, đơn thuốc, …            |
| `/api/store/`            | Logic bán hàng / đơn online — ưu tiên trong `storeApp` |


## Ghi chú cấu trúc `storeApp`

- `storeApp.models` đã tách thành package theo domain để dễ bảo trì:
  - `storeApp/models/product.py`: product, category, brand, variant, batch, notification, search keyword.
  - `storeApp/models/order.py`: order, order item, shipping/payment method.
  - `storeApp/models/voucher.py`: voucher và redemption.
  - `storeApp/models/cart.py`: placeholder cho cart domain.
- `storeApp/models/__init__.py` re-export model để giữ tương thích import cũ (`from storeApp.models import ...`).

Cập nhật file này khi thêm app Django mới, đổi mount URL gốc, hoặc tách/hợp store API.

## Campaign (storeApp) — permissions & URLs

Locked plan for Job `campaign` (P0-T2): see [`docs/campaign-permissions-urls.md`](campaign-permissions-urls.md).

- Public: `/api/store/campaigns/`, `/api/store/campaigns/placements/`, `/api/store/campaigns/{slug}/`
- Admin: `/api/store/admin/campaigns/...` (numeric id)
- Permissions: `storeApp.campaign_view` / `storeApp.campaign_manage` (contract names `store.campaign.view` / `store.campaign.manage`)

## Doctor taxonomy — Khoa vs Chuyên khoa (SoT)

| Khái niệm | Model / code | Dùng để |
|-----------|--------------|---------|
| **Role** | `UserRole` (`ROLE_DOCTOR`, …) | Auth / permission — **không** = chuyên môn |
| **Chuyên khoa** | `SpecializationTag` M2M ↔ `DoctorProfile.specializations` | BN filter khi booking; nurse cover cùng chuyên khoa |
| **Khoa (Department)** | *Chưa có* | Org / roster / báo cáo — chỉ thêm khi có user story HR |

**Rules:**

1. Giữ **M2M** BS ↔ nhiều chuyên khoa (UI booking hiện nhiều tag / card).
2. Không nhét khoa/chuyên khoa vào Django `Group` hoặc `UserRole`.
3. Khi cần Khoa: thêm `Department` 1→N `SpecializationTag`; booking vẫn filter theo **Specialty**, không bắt chọn Khoa trước.
4. Cover doctor (`schedule_cover`) tiếp tục theo shared specialization IDs.
