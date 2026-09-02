# Smart Medicine Cabinet — storeApp API

**Status:** Shipped (PR #82 → `dev`, PR #83 → `main`)  
**SoT app:** `storeApp` under prefix `/api/store/`  
**Plans:** `PersonalProject/plans/[Done] smart-medicine-cabinet.plan.md`, `[Done] smart-cabinet-adjacent-domains.plan.md`

---

## Will / will not

| Will | Will not |
|------|----------|
| Personal home inventory per authenticated store user | Warehouse stock (`MedicineBatch`, `stock.py`) |
| Manual expiry date on every item | Infer HSD from order batch / prescription |
| In-app HSD inbox (`CabinetAlert`) | Reuse warehouse `Notification` |
| Seed cabinet from owned prescriptions (read mainApp, write store) | Auto-seed at checkout; clinic FE changes |
| Buy-again handled on storefront cart API | Decrement cabinet qty on buy-again |

---

## Domain model

**Code:** `storeApp/models/cabinet.py`  
**Migrations:** `0018_cabinet_and_cabinet_item`, `0019_cabinet_p2_fields`, `0020_cabinet_alert`

| Model | Table | Notes |
|-------|-------|-------|
| `Cabinet` | `store_cabinet` | `user_id` (integer, no FK to `mainApp.User`); settings `reminder_enabled`, `expiring_soon_days` (default 30) |
| `CabinetItem` | `store_cabinet_item` | FK `product_variant`, `product_variant_unit`; qty, `expiration_date`, optional `lot_number`, `low_stock_threshold`, `on_refill_list` |
| `CabinetAlert` | `store_cabinet_alert` | Inbox row; `kind` = `EXPIRED` \| `EXPIRING_SOON`; soft link `cabinet_item` (SET_NULL on delete) |

**Computed (not stored):**

- `expiration_status`: `EXPIRED` \| `EXPIRING_SOON` \| `EXPIRING` \| `SAFE` (90-day window for `EXPIRING`)
- `inventory_status`: `IN_STOCK` \| `LOW_STOCK` \| `OUT_OF_STOCK` (default threshold 5)
- No unique constraint on `(cabinet, variant)` — same SKU may appear on multiple rows (different lots/HSD)

**First list:** `GET /cabinets/` auto-creates default cabinet `"Tủ thuốc gia đình"` when user has none.

**Last cabinet:** `DELETE /cabinets/{id}/` returns **400** if it is the user's only cabinet.

---

## Auth

All endpoints below: **`IsAuthenticated`** (store JWT/session user).  
Querysets scoped by `request.user.id` → `Cabinet.user_id` / `CabinetAlert.user_id`.  
Cross-user access → **403 PermissionDenied**.

---

## URL table

Base: **`/api/store/`** (mounted via `mainApp` → `storeApp.urls`).

Catch-all category slug regex **excludes** `cabinets`, `cabinet-items`, `cabinet-alerts`, `cabinet-prescription-lines` (see `storeApp/urls.py`).

### Cabinets

| Method | Path | Notes |
|--------|------|-------|
| GET | `/cabinets/` | List user cabinets; creates default if empty |
| POST | `/cabinets/` | Body: `name`, optional `reminder_enabled`, `expiring_soon_days` |
| GET | `/cabinets/{id}/` | Detail |
| PATCH | `/cabinets/{id}/` | Rename / settings |
| DELETE | `/cabinets/{id}/` | Blocked when only one cabinet remains |
| GET | `/cabinets/{id}/overview/` | Aggregated counts + capped lists (expired, soon, low-stock, refill) |

### Cabinet items

| Method | Path | Notes |
|--------|------|-------|
| GET | `/cabinet-items/` | Query: `cabinet`, `expiration_status` |
| POST | `/cabinet-items/` | Requires `cabinet`, variant + unit IDs, `quantity`, `expiration_date` |
| GET | `/cabinet-items/{id}/` | Detail |
| PATCH | `/cabinet-items/{id}/` | Partial update (qty, HSD, lot, threshold, refill flag) |
| DELETE | `/cabinet-items/{id}/` | **204** empty body |

Serializer exposes hydrated catalog fields: `product_name`, `packing`, `unit_name`, `image_url`, plus computed status fields.

### Cabinet alerts (inbox)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/cabinet-alerts/` | Query: `unread=1` for unread only; ordered newest first |
| GET | `/cabinet-alerts/{id}/` | Detail |
| POST | `/cabinet-alerts/{id}/mark-read/` | Marks single alert read |
| POST | `/cabinet-alerts/mark-all-read/` | Bulk mark; returns `{ "updated": N }` |

### Prescription seed (read-only list)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/cabinet-prescription-lines/` | Owner-only lines from mainApp prescriptions; query `limit` (1–200, default 100) |

**Service:** `storeApp/services/cabinet_prescription_seed.py` — hydrates store catalog where variant exists; orphan lines omitted from selectable seed.

---

## Background job

| Command | Purpose |
|---------|---------|
| `python manage.py scan_cabinet_expiry_alerts` | Daily scan → create `CabinetAlert` for expired / expiring-soon items |

**Behaviour** (`storeApp/services/cabinet_alert_scan.py`):

- Skips cabinets with `reminder_enabled=False`
- Dedupe: same `cabinet_item` + `kind` within **7 days** (override `--dedupe-days`)
- Does **not** create warehouse notifications

**Ops:** schedule via cron / Celery Beat (not required to ship code).

---

## Tests

| File | Coverage |
|------|----------|
| `storeApp/tests/test_cabinet.py` | CRUD, overview, filters, last-cabinet guard |
| `storeApp/tests/test_cabinet_alerts.py` | Scan, dedupe, reminder off, mark-read |
| `storeApp/tests/test_cabinet_prescription_seed.py` | Owner-only, catalog hydrate, limits |

```bash
python manage.py test storeApp.tests.test_cabinet storeApp.tests.test_cabinet_alerts storeApp.tests.test_cabinet_prescription_seed -v 2 --settings=OUPharmacyManagementApp.settings_test
```

---

## Related code map

| Area | Path |
|------|------|
| Viewsets | `storeApp/viewsets/cabinet.py`, `cabinet_alert.py`, `cabinet_prescription.py` |
| Serializers | `storeApp/serializers_cabinet.py`, `serializers_cabinet_alert.py` |
| URL registration | `storeApp/urls.py` |
