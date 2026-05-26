# Products Manual Test Checklist

## Context

- Date:
- Tester:
- Branch/commit:
- Environment:

## Scope

- Product listing/search/filter endpoints:
  - Category listing by slug
  - Search endpoint
  - Dynamic filter endpoint (if impacted)

## Preconditions

- Categories with active products
- Products with mixed stock and price ranges
- At least one product with multiple variants/units

## Scenarios

### A. Listing behavior

- Category page returns paginated products
- Ordering works (default and explicit ordering)
- No pagination warning due to unordered queryset

### B. Filters

- Price range filters return expected subsets
- In-stock filter works
- Brand/category filters work

### C. Search relevance

- Exact match ranks above partial matches
- Search returns stable pagination between page 1/page 2

### D. Regression

- Product serializer fields unchanged for FE contract
- Image URL and price fields remain valid

## Evidence

- API responses:
- Logs:
- Notes:

## Result

- Overall: PASS / PARTIAL / FAIL
- Follow-ups: