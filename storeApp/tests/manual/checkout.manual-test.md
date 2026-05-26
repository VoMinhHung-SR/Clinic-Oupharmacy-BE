# Checkout Manual Test Checklist

## Context

- Date:
- Tester:
- Branch/commit:
- Environment:
- Related docs:
  - `.cursor/cart-checkout-selection-summary.md`

## Scope

- Cart checkout endpoints:
  - `POST /carts/checkout/`
  - `PATCH /carts/items/{item_id}/`
  - `POST /carts/recalculate/`

## Preconditions

- Auth user with ACTIVE cart
- Shipping method available
- Payment method available
- Optional vouchers for discount checks

## Test Strategy

- Group by checkout/cart domain flow.
- Priority:
  - P0 = must pass before plan Done
  - P1 = should pass
  - P2 = edge/regression

## Scenarios

### P0 - Core flows (must pass)

#### Group: Checkout lifecycle

- Endpoints:
  - `POST /carts/checkout/`
- Invariant(s):
  - Checkout creates exactly one order per request.
  - Paid lines are removed from cart.
- Cases:
  - P0-CL-01: Full checkout (no `cart_item_ids`) succeeds and marks cart checked out
  - P0-CL-02: Partial checkout (`cart_item_ids`) succeeds and cart remains ACTIVE with remaining lines
  - P0-CL-03: Checkout totals match cart summary/order totals

#### Group: Packaging switch before checkout

- Endpoints:
  - `PATCH /carts/items/{item_id}/`
  - `POST /carts/checkout/`
- Invariant(s):
  - Changed unit persists into OrderItem.
  - Unit price snapshot follows selected unit.
- Cases:
  - P0-PK-01: Change `product_variant_unit_id` then checkout; OrderItem keeps expected unit
  - P0-PK-02: Change unit updates line price and checkout total correctly

### P1 - Business rules & failures

#### Group: Validation

- Endpoints:
  - `POST /carts/checkout/`
  - `PATCH /carts/items/{item_id}/`
- Invariant(s):
  - Invalid input never creates order.
- Cases:
  - P1-VA-01: Invalid `cart_item_ids` returns 400
  - P1-VA-02: Empty `cart_item_ids` returns 400
  - P1-VA-03: Missing payment method or shipping address returns 400
  - P1-VA-04: Insufficient stock returns error and order is not created

#### Group: Concurrency/version

- Endpoints:
  - `PATCH /carts/items/{item_id}/`
  - `POST /carts/checkout/`
- Invariant(s):
  - Stale cart version must not overwrite newer state.
- Cases:
  - P1-CV-01: Stale `expected_version` returns 409 conflict
  - P1-CV-02: Retry with latest version succeeds without data corruption

### P2 - Edge & regression

#### Group: Regression

- Endpoints:
  - `POST /carts/apply-voucher/`
  - `POST /carts/remove-voucher/`
  - `POST /carts/recalculate/`
- Invariant(s):
  - Voucher and recalc still consistent after unit changes.
- Cases:
  - P2-RG-01: Voucher apply/remove still works after unit change
  - P2-RG-02: Recalculate keeps totals consistent with current lines

## Evidence

- API responses:
- Logs:
- Notes:

## Result

- Overall: PASS / PARTIAL / FAIL
- Follow-ups: