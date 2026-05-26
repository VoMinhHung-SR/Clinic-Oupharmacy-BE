# Manual Test Checklists (BE)

This folder stores feature-level manual test checklists for backend flows.

## Naming

- Use one file per feature flow.
- Suggested format: `<feature>.manual-test.md`
- Examples:
  - `checkout.manual-test.md`
  - `products.manual-test.md`
  - `cart-packaging-switch.manual-test.md`

## How to use

1. Copy `_template.manual-test.md` for a new feature.
2. Fill context (scope, API, env, seed data).
3. Mark each scenario with:
  - `[ ]` not run
  - `[x]` pass
  - `[~]` blocked/partial
4. Add evidence (response snippet, screenshot path, log lines).
5. Add a short release decision at the bottom.

## Status rule

- Keep checklist with `[ ]` while feature is in progress.
- Move to all `[x]` (or documented accepted `[~]`) before marking plan `[Done]`.