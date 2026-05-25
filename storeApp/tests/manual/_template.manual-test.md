#  Manual Test Checklist

## Context

- Date:
- Tester:
- Branch/commit:
- Environment (local/staging):
- Related plan/doc:

## Scope

- In-scope endpoints/services:
- Out-of-scope:

## Preconditions

- Required seed data:
- Required user/account:
- Required vouchers/shipping/payment:

## Test Strategy

- Group by **domain flow** (not only by model/table).
- Prioritize by risk:
  - **P0**: must pass before marking plan `[Done]`
  - **P1**: should pass for release confidence
  - **P2**: edge/regression, run based on time/risk

## Scenarios

### P0 - Core flows (must pass)

#### Group: 

- Endpoints:
- Invariant(s):
- Cases:
  - : 
  - : 

#### Group: 

- Endpoints:
- Invariant(s):
- Cases:
  - : 
  - : 

### P1 - Business rules & failures

#### Group: Validation

- Endpoints:
- Invariant(s):
- Cases:
  - : 
  - : 

#### Group: Concurrency/version

- Endpoints:
- Invariant(s):
- Cases:
  - : 
  - : 

### P2 - Edge & regression

#### Group: Regression

- Endpoints:
- Invariant(s):
- Cases:
  - : 
  - : 

## Evidence

- API responses:
- Logs:
- Screenshots:

## Result

- Overall: PASS / PARTIAL / FAIL
- Release note:
- Follow-ups: