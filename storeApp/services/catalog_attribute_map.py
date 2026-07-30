"""
Map source-catalog attribute codes → store CatalogAttribute.code.

Spike SoT (listing `__NEXT_DATA__.props.pageProps.viewData.filterAttributes`
and PDP `pageProps.product`):

| Source code   | Listing filter label     | Store code      | Notes                          |
|---------------|--------------------------|-----------------|--------------------------------|
| objectUse     | Đối tượng sử dụng        | target_user     | list[str] on PDP               |
| skin          | Loại da                  | skin_type       | cosmetics categories           |
| flavor        | Mùi vị / Mùi hương       | flavor          | list[str]                      |
| indications   | Chỉ định                 | indication      | list[str]                      |
| dosageForm    | Dạng bào chế             | dosage_form     | often scalar string on cards   |
| brandOrigin   | Xuất xứ thương hiệu      | brand_origin    | scalar / badge.attributeName   |
| manufactor    | Nước sản xuất            | (skip attr)     | use Brand.country / packing_meta |
| brand         | Thương hiệu              | (skip)          | Product.brand FK               |
| category      | Danh mục                 | (skip)          | Category tree                  |
| priceSystem   | Giá bán                  | (skip)          | price_range facets             |
| prescription  | Loại thuốc               | (skip v1)       | not in dictionary yet          |

Scraper should export per product (JSON preferred):

```json
"attributes": {
  "objectUse": ["Người lớn", "Trẻ em"],
  "skin": ["Da khô"],
  "flavor": ["Vị Cam"],
  "indications": ["Mụn"],
  "dosageForm": "Gel",
  "brandOrigin": "Pháp"
}
```

Flat CSV columns also accepted: `attributes.objectUse`, `objectUse`, etc.
"""

from __future__ import annotations

# Source catalog codes we import into ProductAttributeValue.
SOURCE_TO_STORE_ATTR = {
    "objectUse": "target_user",
    "object_use": "target_user",
    "skin": "skin_type",
    "skinType": "skin_type",
    "flavor": "flavor",
    "indications": "indication",
    "indication": "indication",
    "dosageForm": "dosage_form",
    "dosage_form": "dosage_form",
    "brandOrigin": "brand_origin",
    "brand_origin": "brand_origin",
}

# Source codes intentionally NOT written as CatalogAttribute values.
SOURCE_ATTR_SKIP = frozenset(
    {
        "brand",
        "category",
        "priceSystem",
        "price_system",
        "manufactor",  # country → Brand.country / packing_meta.origin
        "manufacturer",
        "prescription",
        "productTypes",
        "specification",
        "producer",
        "priceRanges",
    }
)

# Flat row keys (after flatten_dict) that may carry attribute payloads.
FLAT_ATTR_KEYS = (
    "attributes",
    "product.attributes",
    # Direct source codes (PDP / enriched scrape)
    "objectUse",
    "product.objectUse",
    "attributes.objectUse",
    "skin",
    "product.skin",
    "attributes.skin",
    "flavor",
    "product.flavor",
    "attributes.flavor",
    "indications",
    "product.indications",
    "attributes.indications",
    "dosageForm",
    "product.dosageForm",
    "attributes.dosageForm",
    "brandOrigin",
    "product.brandOrigin",
    "attributes.brandOrigin",
    "product.brandOriginBadges.attributeName",
)
