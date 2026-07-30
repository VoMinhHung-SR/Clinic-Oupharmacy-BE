# Catalog attribute scrape spike (P1b)

> Date: 2026-07-30  
> Goal: confirm where filter attributes live in the **source catalog** HTML/JSON so scraper + import can feed `ProductAttributeValue`.

## Findings

### Listing page (`__NEXT_DATA__`)

Path:

`props.pageProps.viewData.filterAttributes[]`

Each item:

```json
{ "id": 15, "name": "Đối tượng sử dụng", "code": "objectUse", "rank": 3, "values": ["Trẻ em", "Người lớn"] }
```

Also:

- `viewData.priceAttribute` — price buckets (already covered by `/search/` `price_ranges`)
- `viewData.sortingAttributeCodes` — ordered facet codes for that category
- Listing product cards often expose only `dosageForm` + `brandOriginBadges` (not full multi-select attrs)

Category diversity (examples):

| Category style | Typical `filterAttributes` codes |
|----------------|----------------------------------|
| Personal care  | objectUse, flavor, manufactor, indications, brand, brandOrigin, dosageForm, category (+ price) |
| Cosmeceuticals | objectUse, skin, manufactor, indications, brand, brandOrigin (+ price); dosageForm may be absent |

### PDP (`__NEXT_DATA__`)

Path: `props.pageProps.product`

Useful fields:

| Field | Type | Maps to store |
|-------|------|---------------|
| `objectUse` | list | `target_user` |
| `skin` | list | `skin_type` |
| `flavor` | list | `flavor` |
| `indications` | list | `indication` |
| `dosageForm` | string | `dosage_form` |
| `brandOrigin` / `brandOriginBadges.attributeName` | string | `brand_origin` |
| `manufactor` | string | **not** attr — `Brand.country` / `packing_meta.origin` |
| `brand` | string | `Product.brand` |

Note: some PDPs return **empty lists** for `objectUse` / `skin` / `flavor` / `indications` even when listing filters show those dimensions. Scraper must prefer PDP when populated; otherwise may need listing enrichment / alternate API later.

## Import skeleton

- Map table: `storeApp/services/catalog_attribute_map.py`
- Upsert helper: `catalog_import/store_import_attributes.py`
- Hook: after `upsert_product_from_row` in `store_import_csv._process_row`
- Dictionary gate: `manage.py seed_catalog_attributes` must run first

Preferred scrape payload:

```json
"attributes": {
  "objectUse": ["Người lớn"],
  "skin": ["Da khô"],
  "flavor": ["Vị Cam"],
  "indications": ["Mụn"],
  "dosageForm": "Gel",
  "brandOrigin": "Pháp"
}
```

## Next scraper work (outside this BE skeleton)

1. Extend product export schema with `attributes` object from PDP fields above.
2. Re-scrape priority categories (personal care, cosmeceuticals, supplements).
3. Re-import → verify `/search/?category=` returns `facets.attributes` with real counts.
4. Optional later: replace-mode for PAV (skeleton is additive only).
