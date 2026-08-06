# Campaign — Permission codenames & URL plan

**Job:** `campaign` · **Task:** P0-T2  
**Status:** Locked for P1+ implementation  
**Align with:** `PersonalProject/jobs/campaign/api.md`  
**SoT app:** `storeApp` under prefix `/api/store/`

---

## Will / will not (this note)

| Will | Will not |
|------|----------|
| Name Django permission codenames + full URL table | Implement models, views, or migrations |
| Map admin vs public routing to avoid slug/id clash | Change voucher_engine or order discount math |
| Document how clinic staff groups should attach | Seed roles in DB in this tick |

---

## Permission codenames

Job contract names (from `api.md`) and Django registration target:

| Contract name (`api.md`) | Django `Meta.permissions` (storeApp) | Capabilities |
|--------------------------|--------------------------------------|--------------|
| `store.campaign.view` | `("campaign_view", "Can view store campaigns")` | Admin GET list + detail (any status) |
| `store.campaign.manage` | `("campaign_manage", "Can manage store campaigns")` | Create/update/actions/replace placements/products/categories/vouchers |

**Runtime checks (P1):**

- Prefer custom DRF permission classes that require **staff** + the matching Django permission (same pattern family as other store admin surfaces using `IsAdminUser`, then tighten to codenames when wiring clinic groups).
- `campaign_manage` **implies** view for action endpoints (do not require both on every write if manage is present).
- **Anonymous / authenticated customer:** public GETs only (`AllowAny` or equivalent) — no campaign admin permissions.
- **Operator pause-only (feature role):** still use `campaign_manage` for pause/resume in v1, or soft-stop if product wants a separate `campaign_operate` later (not in current `api.md`).

**Group mapping (ops):**

| Clinic / staff intent | Attach permissions |
|-----------------------|--------------------|
| Marketer / campaign editor | `storeApp.campaign_view` + `storeApp.campaign_manage` |
| Read-only campaign auditor | `storeApp.campaign_view` only |
| Storefront customer / guest | none |

Exact Group names live in mainApp/auth ops; Campaign does not invent a new auth stack (D-02).

---

## Final URL table (API)

Base: **`/api/store/`** (already mounted via `mainApp` → `storeApp.urls`).

### Public (slug-based; invisible → identical `404`)

| Method | Full path | Auth | Notes |
|--------|-----------|------|-------|
| GET | `/api/store/campaigns/` | Public | Active-in-window list only |
| GET | `/api/store/campaigns/placements/` | Public | **Static segment before slug** — register before detail |
| GET | `/api/store/campaigns/{slug}/` | Public | Active-in-window detail by **slug** |

### Admin (numeric id; staff + permissions)

| Method | Full path | Permission | Notes |
|--------|-----------|------------|-------|
| GET | `/api/store/admin/campaigns/` | view or manage | All statuses |
| POST | `/api/store/admin/campaigns/` | manage | Create draft |
| GET | `/api/store/admin/campaigns/{id}/` | view or manage | Numeric **id** |
| PATCH | `/api/store/admin/campaigns/{id}/` | manage | Requires `version` |
| POST | `/api/store/admin/campaigns/{id}/schedule/` | manage | → scheduled |
| POST | `/api/store/admin/campaigns/{id}/publish/` | manage | → active (`publish_now` / D-04) |
| POST | `/api/store/admin/campaigns/{id}/pause/` | manage | → paused |
| POST | `/api/store/admin/campaigns/{id}/resume/` | manage | paused → active |
| POST | `/api/store/admin/campaigns/{id}/end/` | manage | → ended |
| POST | `/api/store/admin/campaigns/{id}/archive/` | manage | → archived |
| PUT | `/api/store/admin/campaigns/{id}/placements/` | manage | Full replace |
| PUT | `/api/store/admin/campaigns/{id}/products/` | manage | Full replace MIDs |
| PUT | `/api/store/admin/campaigns/{id}/categories/` | manage | Full replace slugs |
| PUT | `/api/store/admin/campaigns/{id}/vouchers/` | manage | Full replace voucher links |

### Related (existing) — do not rename

| Method | Full path | Notes |
|--------|-----------|-------|
| POST | `/api/store/orders/` (existing) | Optional body field `campaign_id` (P5); invalid ignored |
| POST | Cart apply-voucher (existing) | Discount math stays in `voucher_engine` |

---

## Routing rules (no ambiguity)

1. **Public uses `slug`; admin uses numeric `id`.** Never put admin under `/campaigns/{id}/` without the `admin/` prefix.
2. Register **`campaigns/placements/`** before **`campaigns/<slug>/`** so `placements` is not captured as a slug.
3. Exclude new router names from the category catch-all regex in `storeApp/urls.py` when implementing (today’s negative lookahead list must gain `campaigns` and `admin`).
4. Storefront paths (not Django): `/khuyen-mai`, `/khuyen-mai/[slug]` — CTA `cta_url` must be site-relative starting with `/` (D-09).

---

## PR checklist (verification for implementers)

Copy into P1 PR description:

- [ ] Permissions registered: `campaign_view`, `campaign_manage` on Campaign (or AppConfig ready)
- [ ] Public paths match table (list / placements / slug detail)
- [ ] Admin paths under `/api/store/admin/campaigns/`
- [ ] `placements` not treated as slug
- [ ] Category catch-all excludes `campaigns` + `admin`
- [ ] 401/403 on admin without auth/permission; public never leaks drafts (404)

---

## Cross-links

- Contract detail: `jobs/campaign/api.md`
- Decisions: `jobs/campaign/decisions.md` (D-02, D-06, D-09)
- Architecture pointer: `docs/ARCHITECTURE.md` § Campaign
