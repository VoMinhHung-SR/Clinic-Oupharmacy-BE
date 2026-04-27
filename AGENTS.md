# Clinic-Oupharmacy-BE — Agent & contributor map

**Django** + **Django REST Framework** + **PostgreSQL**. API cho clinic admin và **store** (`storeApp`); JWT / OAuth2 / Firebase social (xem `mainApp`).

## Cấu trúc chính


| Path                       | Vai trò                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| `OUPharmacyManagementApp/` | Settings, root `urls.py`                                                                   |
| `mainApp/`                 | Router DRF, viewsets, auth views, `urls.py` gắn `api/store/`                               |
| `storeApp/`                | API storefront (đơn hàng, sản phẩm store, …)                                               |
| `config/`                  | Cấu hình bổ sung (nếu có)                                                                  |
| `manage.py`                | Django CLI                                                                                 |
| `scripts/db/`              | Backup DB — **xem rule** `.cursor/rules/no-volume-before-backup.mdc` trước khi động volume |


## Đi vào đâu theo việc


| Việc                            | Bắt đầu từ                                                                   |
| ------------------------------- | ---------------------------------------------------------------------------- |
| REST resource / serializer mới  | `mainApp/viewsets/`, `mainApp/serializers/` (hoặc pattern hiện có trong app) |
| URL API chính                   | `mainApp/urls.py` → `router` + `urlpatterns`                                 |
| Store API (prefix `api/store/`) | `storeApp/urls.py`, `storeApp/views` / viewsets                              |
| Auth / OAuth / Firebase         | `mainApp/views.py`, `mainApp/urls.py` (`oauth2-info/`, `auth/...`)           |
| Model / migration               | App tương ứng (`mainApp`, `storeApp`, …)                                     |


## Lệnh thường dùng

```bash
# Trong venv
python manage.py runserver
python manage.py migrate
python manage.py test
```

Docker / DB: tuỳ `docker-compose`; **không** `docker-compose down -v` khi chưa backup (rule volume).

## Bảo mật

- Không commit `.env` / secret; không paste credential vào chat.

## Plans

- Plan feat: `Clinic-Oupharmacy-BE/.cursor/plans/` — tên file `**[UnDone]` / `[Done]`** (xem `PersonalProject/.cursor/rules/planning-project-plans-folder.mdc`).

