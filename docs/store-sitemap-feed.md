# Store product sitemap feed

**SoT:** `storeApp` · `GET /api/store/products/sitemap/`  
**Consumers:** `oupharmacy-store` `src/app/sitemap.ts` (via `getProductSitemapEntriesSSG`)

## Purpose

Lightweight list of active product URL paths for storefront `sitemap.xml`. No heavy product serializers.

## Response shape

Paginated (`page`, `page_size`; default 500, max 2000):

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "slug": "paracetamol-500mg",
      "path": "thuoc/paracetamol-500mg",
      "updated_at": "2026-09-30T12:00:00+07:00"
    }
  ]
}
```

| Field | Meaning |
|-------|---------|
| `slug` | `Product.slug` |
| `path` | `{category.path_slug\|slug}/{product.slug}` (canonical PDP path without leading `/`) |
| `updated_at` | `Product.updated_date` ISO-8601 |

Inactive products and empty slugs are omitted. Auth: **AllowAny**.
