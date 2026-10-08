# Consultation Hub — Backend (Clinic-Oupharmacy-BE)

Storefront consultation hub: pharmacist sessions live in **storeApp**; doctor/medicine branches reuse existing MAIN_API (no extra consultation tables).

## Domain

**`storeApp.ConsultationSession`** (`storeApp/models/consultation.py`) — pharmacist only:

| Field | Notes |
|-------|--------|
| `user_id` | Customer |
| `pharmacist_id` | Nullable until claim |
| `status` | `WAITING_FOR_PROFESSIONAL` \| `IN_PROGRESS` \| `COMPLETED` \| `CANCELLED` |
| `firestore_conversation_id` | Chat transport (not Django messages) |
| `need_text` | Optional seed / escalate text |
| `context_json` | Optional product / source payload |

Messages: **Firestore** only (`${APP_ENV}_messages`, …).

## Role

- `ROLE_PHARMACIST` in `mainApp/constant.py` (+ data migration seed).
- Queue/claim requires this role (not nurse).

## API — `/api/store/consultation-sessions/`

| Method | Action |
|--------|--------|
| `POST /` | Create **or reuse** open session (idempotent): if customer already has `WAITING_FOR_PROFESSIONAL` / `IN_PROGRESS`, return that row (**200**) and merge non-empty `need_text` / `context_json`; otherwise create (**201**) |
| `GET /?scope=mine` | Customer’s sessions |
| `GET /?scope=queue&status=WAITING_FOR_PROFESSIONAL` | Pharmacist queue |
| `GET /{id}/` | Retrieve |
| `PATCH /{id}/` | Update `firestore_conversation_id` / `need_text` / `context_json` |
| `POST /{id}/claim/` | Atomic claim (`select_for_update`) |
| `POST /{id}/complete/` | Complete |
| `POST /{id}/cancel/` | Cancel |

Claim service: `storeApp/services/consultation/pharmacist_queue.py`.  
Idempotent create: `storeApp/services/consultation/session_create.py` (`get_or_create_open_session`).  
Tests: `storeApp/tests/test_consultation_session.py`.

## Doctor / medicine (no new BE models)

| Branch | Existing MAIN / store APIs |
|--------|----------------------------|
| Doctor | `common-configs/`, `doctor-schedules/schedule/`, `time-slots/`, `patients/`, `examinations/` |
| Medicine | `GET /api/store/search/` + cart (storefront) |

## Key files

| Path | Why |
|------|-----|
| `storeApp/models/consultation.py` | Model |
| `storeApp/viewsets/consultation_session.py` | ViewSet |
| `storeApp/serializers_consultation.py` (or package equiv.) | Serializers |
| `storeApp/urls.py` | Router register |
| `mainApp/constant.py` | `ROLE_PHARMACIST` |

## Plans

- `PersonalProject/plans/[Done] consultation-hub-mvp.plan.md`
- Local copy: [`docs/planning/consultation.plan.md`](planning/consultation.plan.md)
