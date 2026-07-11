# Clinic-Oupharmacy-BE — Agent & contributor map

**Django** + **Django REST Framework** + **PostgreSQL**. API cho clinic admin và **store** (`storeApp`); JWT / OAuth2 / Firebase social (xem `mainApp`).

## Cấu trúc chính


| Path                       | Vai trò                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| `OUPharmacyManagementApp/` | Settings, root `urls.py`                                                                   |
| `mainApp/`                 | Router DRF, viewsets, auth views, `urls.py` gắn `api/store/`                               |
| `storeApp/`                | API storefront (đơn hàng, sản phẩm store, …)                                               |
| `config/`                  | Cấu hình bổ sung (nếu có)                                                                  |
| `manage.py`                | Django CLI                                                                                 |
| `scripts/db/`              | Backup DB — **xem rule** `.cursor/rules/no-volume-before-backup.mdc` trước khi động volume |


## Đi vào đâu theo việc


| Việc                            | Bắt đầu từ                                                                   |
| ------------------------------- | ---------------------------------------------------------------------------- |
| REST resource / serializer mới  | `mainApp/viewsets/`, `mainApp/serializers/` (hoặc pattern hiện có trong app) |
| URL API chính                   | `mainApp/urls.py` → `router` + `urlpatterns`                                 |
| Store API (prefix `api/store/`) | `storeApp/urls.py`, `storeApp/views` / viewsets                              |
| Auth / OAuth / Firebase         | `mainApp/views.py`, `mainApp/urls.py` (`oauth2-info/`, `auth/...`)           |
| Model / migration               | App tương ứng (`mainApp`, `storeApp`, …)                                     |


## Lệnh thường dùng

```bash
# Trong venv
python manage.py runserver
python manage.py migrate
python manage.py test

# Regression — SQLite dual-DB (khớp GitHub Actions)
python manage.py test storeApp.tests -v 2 --settings=OUPharmacyManagementApp.settings_test
python manage.py test mainApp.tests -v 2 --settings=OUPharmacyManagementApp.settings_test
```

**CI (PR → `dev` / `main`):**

| Workflow | Suite |
|----------|--------|
| `.github/workflows/test-storeapp.yml` | `storeApp.tests` — cart, checkout, search, category M2M |
| `.github/workflows/test-mainapp.yml` | `mainApp.tests` — diagnosis suggestions, password reset |

Plan: `PersonalProject/plans/[UnDone] clinic-be-ci-tests.plan.md`

Docker / DB: tuỳ `docker-compose`; **không** `docker-compose down -v` khi chưa backup (rule volume).

## Bảo mật

- Không commit `.env` / secret; không paste credential vào chat.

## Plans

- Plan feat: `Clinic-Oupharmacy-BE/.cursor/plans/` — tên file `**[UnDone]` / `[Done]`** (xem `PersonalProject/.cursor/rules/planning-project-plans-folder.mdc`).

## Store search & facets (storeApp)

| Doc | Nội dung |
|-----|----------|
| `storeApp/guidelines/search-faceted-api.md` | SoT API `/search/`, query params, facet semantics |
| `storeApp/guidelines/search-facets-migration-2026-07-10.md` | Breaking: xóa `/dynamic-filters/`, rebuild checklist |
| `storeApp/services/search_facets_service.py` | Facet SQL + versioned cache |

Sau đổi `views.py` / `urls.py` store: `docker compose build backend && docker compose up -d backend`.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Clinic-Oupharmacy-BE** (3968 symbols, 6192 relationships, 185 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Clinic-Oupharmacy-BE/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Clinic-Oupharmacy-BE/clusters` | All functional areas |
| `gitnexus://repo/Clinic-Oupharmacy-BE/processes` | All execution flows |
| `gitnexus://repo/Clinic-Oupharmacy-BE/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
