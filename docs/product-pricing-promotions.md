# Product pricing & promotions — ADR (Option 1)

**Status:** Accepted (P0 — 2026-08-28; P1 shipped — 2026-08-28)  
**Plan:** `PersonalProject/plans/[UnDone] catalog-pricing-direct-discount-refactor.plan.md`  
**Repos:** `Clinic-Oupharmacy-BE` (SoT), `oupharmacy-store` (display + cart UX)

---

## Context

Storefront cần hai lớp giảm giá tách biệt (chuẩn Long Châu / pharmacy e-commerce):

1. **Giảm giá sản phẩm (catalog / direct)** — giá dòng hàng đã là giá sale; tiết kiệm = list − sale.
2. **Giảm giá đơn hàng (voucher)** — mã `ORDER_DISCOUNT` / `SHIPPING_DISCOUNT` qua `voucher_engine`.

Trước refactor, hệ thống có thể gán `compare_at_price` **tính ngược** từ `price_value` (badge −% nhưng checkout không hạ tiền). FE giỏ copy banner Long Châu nhưng `directDiscount` chưa map đúng field BE.

---

## Decision — locked rules (D-PRC)

### D-PRC-01 — Server is single source of truth

| Client gửi | Client **không** gửi |
|------------|------------------------|
| `product_variant_id`, `product_variant_unit_id`, `quantity` | `original_price`, `compare_at`, `discount_percent` |
| `expected_version` (cart mutate) | Công thức % tự tính để “ép” giá checkout |
| `order_voucher_code`, `shipping_voucher_code` | |

Server resolve giá tại **add-to-cart**, **recalculate**, **checkout**. Order lưu `unit_price_snapshot`.

### D-PRC-02 — Two discount layers

| Layer | Mechanism | Affects money |
|-------|-----------|---------------|
| **Catalog / product** | `ProductVariantUnit.price_value`, `compare_at_price`; future `ProductUnitPromotion` | **Yes** — via sale price in cart subtotal |
| **Order voucher** | `storeApp.services.voucher_engine` → `discount_amount`, `shipping_discount_amount` | **Yes** — on subtotal / shipping after catalog prices |

Campaign CMS (`Campaign`, `CampaignProduct`, `CampaignVoucher`) = **merch + scope + voucher display**. Campaign **does not** replace pricing engine (see `docs/campaign-permissions-urls.md`).

### D-PRC-03 — Catalog field semantics

| Field | Meaning | Rules |
|-------|---------|--------|
| `price_value` | **Current selling price** | Used for cart snapshot & checkout line total |
| `compare_at_price` | **List / pre-promo reference** | Must be **>** `price_value` when showing a sale; requires **provenance** (sync, import, promotion apply) |
| `discount_percent` (API) | Read-only | `round((compare_at − price) / compare_at × 100)` — not a separate SoT column |

**Provenance (allowed sources for `compare_at`):**

- `sync_mainapp_data`: `MedicineUnit.original_price_value`
- Catalog import when scraper provides real list price (future: `pricing.originalPriceValue`)
- **Promotion apply (P1+):** snapshot list before lowering `price_value`

### D-PRC-04 — Forbidden: reverse compare_at (merch-only)

**Do not** set:

```text
compare_at = price / (1 − percent/100)   while price_value unchanged
```

This creates display-only “fake” discounts. **Banned in new code** after P0.

**Legacy / debt (remove in P4):**

- `seed_hot_sale_campaign` (pre-P1) — sets reverse `compare_at` only
- FE hot-sale synth tiers (removed — Option A catalog-only)
- Flash sale live synth % (D-23) — **follow-up ADR**; out of scope for this plan’s P1–P4

**Valid promotion apply (P1+):**

```text
list_price  = existing compare_at OR current price_value (before promo)
sale_price  = round(list_price × (1 − tier/100))
compare_at  = list_price
price_value = sale_price
```

### D-PRC-05 — Cart display economics (target, P2+)

Aligned with Long Châu receipt copy on `/gio-hang`:

| UI label | Formula | Double-count? |
|----------|---------|---------------|
| Line price | `unit_price_snapshot` (sale) | — |
| **Giảm giá trực tiếp** | `Σ max(0, list_snapshot − sale_snapshot) × qty` | **No** — informational |
| **Tổng tiền (subtotal)** | `Σ sale_snapshot × qty` | Already includes catalog sale |
| **Giảm giá voucher** | `discount_amount + shipping_discount_amount` | Applied on subtotal / ship |
| **Thành tiền** | subtotal − voucher discounts + shipping | |

**Current gap (pre-P2):** BE cart API does not yet expose `catalog_direct_savings_total`. FE `directDiscount` may mislabel voucher slot — fix in P3.

---

## Implementation map

| Phase | BE | FE |
|-------|----|----|
| **P0** (this ADR) | Docs + deprecate reverse seed | Docs + no new reverse merch |
| **P1** ✅ | `product_pricing.py`, `ProductUnitPromotion`, hot-sale seed | Catalog read-only (Option A) |
| **P1b** ✅ | Unified auto revert — mọi `ProductUnitPromotion` (hot-sale, CMS, flash BE) | — |
| **P2** | `catalog_direct_savings_total` on cart | — |
| **P3** | — | Fix `directDiscount` / voucher columns |
| **P4** | Revert bad data; E2E | UAT home → cart → checkout |

---

## Code pointers

| Area | Path |
|------|------|
| Unit prices | `storeApp/models/product.py` → `ProductVariantUnit` |
| Product API | `storeApp/serializers.py` → `get_compare_at_price`, `get_discount_percent` |
| Cart subtotal | `storeApp/services/cart_service.py` → `_build_context`, `recalculate_cart` |
| Voucher | `storeApp/services/voucher_engine.py` |
| Checkout contract | `storeApp/guidelines/cart-first-checkout.md` |
| Pricing helpers | `storeApp/services/product_pricing.py` |
| Hot-sale seed + revert | `storeApp/services/hot_sale_campaign.py`, `ProductUnitPromotion` |
| Promo lifecycle (P1b) | `storeApp/services/product_promotion.py`; hook `run_campaign_scheduler` |
| FE cart mislabel (fix P3) | `oupharmacy-store/src/app/gio-hang/page.tsx` |

---

## Related decisions (unchanged)

- **D-01:** Home merch display ≠ checkout price engine (flash upcoming `-xx%` still display-only until follow-up).
- **D-07 / SC-05:** Campaign voucher list = display; checkout uses `voucher_engine`.
- **Cart-first:** `unit_price_snapshot` at add time; checkout does not re-fetch live catalog price silently.

---

## Catalog promo lifecycle (P1b — unified revert)

**Rule:** Any program that **lowers** `ProductVariantUnit.price_value` for a time window **must**:

1. Create/update a **`ProductUnitPromotion`** row with `previous_price_value`, `previous_compare_at_price`, `starts_at`, `ends_at`, linked **`Campaign`**.
2. Set `source` to one of: `hot_sale` | `cms` | `flash_sale` (extensible CharField — revert logic is **source-agnostic**).
3. Rely on **`revert_expired_unit_promotions(now)`** (hooked from `run_campaign_scheduler`) when `ends_at` passes or campaign → `ended`.

**Not in this lifecycle (no auto revert on unit price):**

| Program | Why |
|---------|-----|
| Flash sale FE synth (D-23 today) | Display merch only — no DB catalog write |
| Brand campaign card `%` | FE display |
| Vouchers | `voucher_engine` — order-level, not unit catalog |

**When flash sale moves to BE catalog apply:** use the same `apply_unit_promotion` path — **no separate revert command**.

**CMS:** Admin must not patch `price_value` without snapshot; future Jazzmin “apply promotion” calls shared service only.

**Overlap (same unit, multiple campaigns):** revert one campaign restores `previous_*` only if no other **active** promo remains on that unit; otherwise keep effective sale price from remaining promo (see plan P1b spike).

---

## Follow-up backlog (post-P0)

| Item | Owner | Note |
|------|-------|------|
| Flash sale live −10…35% synth → BE catalog | PM + BE + FE | Must use `ProductUnitPromotion` + P1b revert when lowering `price_value` |
| CMS apply catalog promotion | BE admin | Caller of shared `apply_unit_promotion`; `source=cms` |
| Brand campaign card `%` | FE | `brandCampaigns.ts` display-only today |
| Importer `originalPriceValue` → `compare_at` | BE catalog | See `plans/[Done] csv-importer-fields-cleanup.plan.md` |
| Auto revert expired promos (P1b) | BE ✅ | `product_promotion.py` + `run_campaign_scheduler` |
| Jazzmin promotion admin | BE | After P1b |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-08-28 | P1b: `product_promotion.py`, auto revert in `run_campaign_scheduler`, overlap by campaign priority |
| 2026-08-28 | P1: `ProductUnitPromotion`, `product_pricing.py`, hot-sale seed lowers sale price |
| 2026-08-28 | P0: ADR accepted; D-PRC-01…05 locked |
