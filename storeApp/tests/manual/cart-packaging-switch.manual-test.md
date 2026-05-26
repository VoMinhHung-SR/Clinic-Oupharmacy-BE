# Cart Packaging Switch Manual Test Checklist

## Context

- Date:
- Tester:
- Branch/commit:
- Environment:
- Related plan/doc:
  - `plans/[UnDone] cart-packaging-switch-full-workflow.plan.md`
  - `.cursor/cart-checkout-selection-summary.md`

## Scope

- Cart item update with packaging/unit switch
- Cart totals + partial checkout compatibility

## Preconditions

- Auth user with ACTIVE cart and at least one line having multiple units
- Available stock for at least two units
- Shipping/payment method available for checkout checks

## Test Strategy

- Group by domain flow and risk (P0/P1/P2).

## Scenarios

### P0 - Core flows (must pass)

#### Group: Unit switch behavior

- Endpoints:
  - `PATCH /carts/items/{item_id}/`
- Invariant(s):
  - Changing unit updates line price and keeps cart consistent.
  - If target unit already exists as another line, lines are merged safely.
- Cases:
  - P0-US-01: Switch unit on one line updates `product_variant_unit_id` and `unit_price_snapshot`
  - P0-US-02: Switch to an already-existing unit merges lines and keeps correct quantity
  - P0-US-03: Cart totals are recalculated correctly after switch

#### Group: Selection + checkout compatibility

- Endpoints:
  - `POST /carts/checkout/`
- Invariant(s):
  - Selected line scope remains valid after unit switch.
- Cases:
  - P0-SC-01: Partial checkout still works with updated lines
  - P0-SC-02: Full checkout after switch creates order with expected units

### P1 - Business rules & failures

#### Group: Validation

- Endpoints:
  - `PATCH /carts/items/{item_id}/`
- Invariant(s):
  - Invalid unit input does not mutate cart.
- Cases:
  - P1-VA-01: Invalid `product_variant_unit_id` returns 400
  - P1-VA-02: Unpublished/foreign unit returns 400
  - P1-VA-03: Insufficient stock after switch returns error

#### Group: Concurrency/version

- Endpoints:
  - `PATCH /carts/items/{item_id}/`
- Invariant(s):
  - Stale version cannot override new cart state.
- Cases:
  - P1-CV-01: Stale `expected_version` returns 409
  - P1-CV-02: Retry with latest version succeeds and state remains correct

### P2 - Edge & regression

#### Group: UX/behavioral stability

- Endpoints:
  - `PATCH /carts/items/{item_id}/`
- Invariant(s):
  - Rapid unit changes do not create inconsistent final state.
- Cases:
  - P2-UX-01: Rapid switch A->B->C applies last choice correctly
  - P2-UX-02: No duplicate lines or negative totals after repeated switches

## Evidence

- API responses:
- Logs:
- Notes/screenshots:

## Result

- Overall: PASS / PARTIAL / FAIL
- Follow-ups: