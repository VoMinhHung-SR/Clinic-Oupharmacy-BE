---
name: Consultation Hub MVP
overview: "LOCKED: ConsultChatbox trên store; FE state machine deterministic (no NLP/LLM). Pharmacist=human Firestore+ConsultationSession. Doctor=guided+booking action qua API hiện có. Medicine=search→1–5 cards+cart. Ready to implement."
todos:
  - id: p0-foundation
    content: "P0 BE: ROLE_PHARMACIST + ConsultationSession + claim/complete + register urls"
    status: completed
  - id: p1-chatbox-shell
    content: "P1 Store: ConsultChatbox + deterministic intent state machine + menu 1/2/3"
    status: completed
  - id: p2-pharmacist
    content: P2 Store Firestore chat + Clinic FE pharmacist queue/claim/inbox
    status: completed
  - id: p3-doctor-actions
    content: "P3 Doctor branch: guided steps + BookingActionBubble → MAIN_API examination/schedule"
    status: completed
  - id: p4-medicine-actions
    content: "P4 Medicine branch: search.ts → ProductSuggestBubble 1–5 + CartContext.add"
    status: completed
isProject: false
---

# Consultation Hub MVP — Final lock (pre-implement)

> PLAN ONLY until you explicitly say implement.  
> Preferred doc path later: `Clinic-Oupharmacy-BE/docs/planning/consultation.plan.md` (copy when implementing).

---

## Intelligence lock (NON-NEGOTIABLE)

> **MVP conversation intelligence is deterministic FE state management. No NLP, LLM, semantic matching, autonomous action selection, or AI-generated medical recommendations.**

| Allowed | Forbidden in MVP |
|---------|------------------|
| Explicit menu `1 \| 2 \| 3` / quick-reply buttons | Parse free-text intent with NLP/LLM |
| Fixed step enums (`menu → pharmacist \| doctor \| medicine → …`) | Autonomous “agent” chọn action |
| Keyword/`q` + category filter qua Store search API | Semantic “cùng công dụng” embedding/similarity |
| Hard-coded system copy + disclaimer | AI medical recommendations |
| User taps form fields / cú pháp **đã document** (regex parse cố định) | Model tự suy ra đặt lịch |

---

## One-line product

**Một chatbox Tư Vấn** trên storefront: điều hướng 3 nhánh bằng state machine; **dược sĩ = human chat**; **bác sĩ = guided + đặt lịch**; **thuốc = search cards + giỏ**.

```text
ConsultChatbox
 ├─ (1) Pharmacist → ConsultationSession → Firestore → Clinic pharmacist
 ├─ (2) Doctor     → FE steps → BookingActionBubble → MAIN_API exams/schedules
 └─ (3) Medicine   → search API → 1–5 cards → CartContext.add
```

---

## What exists / reuse / build / exclude

| Exists | Reuse as-is | Build | Exclude |
|--------|-------------|-------|---------|
| Firestore clinic chat | Message transport pharmacist | `ConsultationSession` + claim API | NLP/LLM/AssistantPort |
| `ROLE_*` + OAuth2 | Auth patterns | `ROLE_PHARMACIST` | Orchestrator god-service |
| Examination + doctor-schedules + time-slots | Doctor book action | ConsultChatbox + FE state machine | `ConsultationRecommendation` model |
| `search.ts` + `CartContext` | Medicine cards + add cart | Rich bubbles (menu, booking, products) | Django Channels / message tables |
| `OfferSheet`, `LoginModal`, FAB-like sticky patterns | Widget chrome | Clinic FE queue UI for pharmacist | Background-jobs phase |
| `/tu-van-duoc-si` placeholder | — (đã xóa route) | CTA → `useConsultUi().open()` | Kommunicate |

---

## Domain (minimal)

**`storeApp.ConsultationSession`** (pharmacist-only):

- `user_id`, `pharmacist_id` (nullable), `status` ∈ `WAITING_FOR_PROFESSIONAL | IN_PROGRESS | COMPLETED | CANCELLED`
- `firestore_conversation_id`, `need_text`, `context_json` (optional product/source)
- No `session_type` multi-enum; no doctor/medicine rows; no Django messages

**API** `/api/store/consultation-sessions/`: `POST`, `GET` (mine|queue), `GET/{id}`, `POST/{id}/claim|complete|cancel`

**Doctor/Medicine:** zero consultation tables — call existing MAIN_API / store search/cart from FE.

---

## FE state machine (deterministic)

```text
idle
 → menu          (show quick replies 1/2/3)
 → pharmacist    (auth gate → create session → Firestore thread)
 → doctor_guide  (fixed prompts: reason → pick schedule UI)
 → doctor_book   (submit examination)
 → medicine_query (ask q / category buttons from known categories API)
 → medicine_results (render ≤5 cards)
 → (any) can return menu
```

Transitions **only** via button click or documented syntax (e.g. doctor book command regex). Free text in pharmacist branch goes to Firestore as human message, **not** interpreted by FE logic.

---

## Implementation phases

| # | Focus | AC |
|---|-------|----|
| **P0** | BE role + session + permissions + tests | User create/list; pharmacist claim atomic |
| **P1** | Chatbox shell + menu state machine in layout | Open FAB; chọn 1/2/3 đổi branch UI |
| **P2** | Pharmacist human path E2E | Store ↔ Clinic FE chat + complete |
| **P3** | Doctor BookingActionBubble | Tạo examination thành công (auth); fallback link `/booking` nếu API lỗi |
| **P4** | Medicine cards + cart | ≤5 results; add cart; `CONSULT` → escalate pharmacist + context |

---

## File / module impact (optimized to current tree)

### A) Clinic-Oupharmacy-BE — create

| Path | Why |
|------|-----|
| `storeApp/models/consultation.py` | `ConsultationSession` |
| `storeApp/migrations/0xxx_consultation_session.py` | store DB |
| `storeApp/serializers_consultation.py` | hoặc `serializers/consultation.py` theo convention gần `medicine_request` |
| `storeApp/viewsets/consultation_session.py` | ViewSet |
| `storeApp/services/consultation/pharmacist_queue.py` | claim `select_for_update` only |
| `storeApp/tests/test_consultation_session.py` | authz + claim race |
| `docs/planning/consultation.plan.md` | optional copy of this plan |

### A) BE — modify

| Path | Why |
|------|-----|
| `storeApp/models/__init__.py` | export model |
| `storeApp/urls.py` | register router |
| `mainApp/constant.py` | `ROLE_PHARMACIST` |
| Role seed / fixture / data migration hoặc management note | ensure role row exists |
| `mainApp/permissions.py` hoặc `storeApp/permissions/…` | pharmacist queue permission |
| `storeApp/admin.py` (nếu có pattern) | list sessions |
| `docs/ARCHITECTURE.md` | 1 đoạn Consultation |

**Không đụng:** Channels, Celery tasks mới, product models, Examination models (chỉ gọi API có sẵn).

### B) oupharmacy-store — create

| Path | Why |
|------|-----|
| `src/components/consultation/ConsultChatbox.tsx` | FAB + panel |
| `src/components/consultation/ConsultMessageList.tsx` | |
| `src/components/consultation/IntentMenuBubble.tsx` | 1/2/3 |
| `src/components/consultation/BookingActionBubble.tsx` | form đặt lịch |
| `src/components/consultation/ProductSuggestBubble.tsx` | 1–5 cards |
| `src/components/consultation/useConsultStateMachine.ts` | deterministic FSM |
| `src/components/consultation/usePharmacistThread.ts` | Firestore |
| `src/lib/services/consultation.ts` | session API |
| `src/lib/consultation/firestore.ts` | collections helpers |
| `src/app/tu-van/page.tsx` | **deleted** — không page hub |

### B) Store — modify

| Path | Why |
|------|-----|
| `src/app/layout.tsx` | mount ConsultChatbox (như LoginModal) |
| `src/lib/config/firebase.ts` | `getFirestore` |
| `src/lib/constant.ts` | `HOME_QUICK_LINKS` `openConsult: true`; `CONSULT_HREF=/?consult=open` |
| `src/app/tu-van-duoc-si/page.tsx` | **deleted** — không giữ redirect |
| `src/i18n/messages/vi.json` | copy hub |
| `src/contexts/CartContext.tsx` | **reuse** `add` — không đổi API trừ export nếu thiếu |
| `src/lib/services/search.ts` | **reuse** — gọi từ medicine branch |
| `src/lib/services/auth.ts` / MAIN_API usage | doctor book qua `NEXT_PUBLIC_MAIN_API_URL` (examinations, schedules) — thin `src/lib/services/booking.ts` **create** nếu chưa có client |

### C) Clinic-Oupharmacy-FE — modify

| Path | Why |
|------|-----|
| `src/lib/constants.js` | `ROLE_PHARMACIST` |
| `src/lib/auth/permissions.js` | `getPostLoginPath` / role checks |
| `src/App.jsx` | allow pharmacist vào dashboard conversations (special role list) |
| `src/modules/pages/ConversationListComponents/SidebarInbox/*` | queue WAITING + claim |
| `src/modules/pages/ChatWindowComponents/*` | nhẹ: filter `pharmacist_consult` / image optional |
| `src/lib/services/index.js` hoặc service mới | gọi store consultation claim/list |

**Reuse không fork:** `config/firebase.js`, `getMessagesInConversation.js`, `useChatWindow.js` pattern.

### D) Explicit non-touch (tránh scope creep)

- `MedicineRequest` / `/dat-thuoc` — giữ độc lập  
- `diagnosis_medicine_suggestions.py` — không port vào store chat  
- `src/chatbot` Kommunicate — không bật  
- Product / PrescriptionDetail schema — không đổi  

---

## Integration map (system-aligned)

| Branch | FE calls | Backend SoT |
|--------|----------|-------------|
| Pharmacist | `consultation.ts` + Firestore | storeApp session + Firestore |
| Doctor | new thin `booking.ts` → MAIN_API (mirror Clinic `BookingComponents/services`) | `doctor-schedules`, `time-slots`, `examinations` |
| Medicine | `search.ts` + `useCart().add` | `/api/store/search/`, cart endpoints |
| Auth gate | `LoginModalContext` | OAuth tokens already on store |

**P3 risk control:** nếu CORS/payload examination phức tạp — ship **fallback** `getClinicBookingUrl()` trong cùng bubble; form-in-chat là target, link là safety net (vẫn deterministic).

**P4 “cùng công dụng”:** chỉ = cùng `q`/category user vừa chọn + search ranking hiện có — **không** semantic engine.

---

## Safety (short)

- No autonomous diagnosis/Rx.  
- Medicine = catalog suggest + disclaimer.  
- `price_display === CONSULT` → không add cart; escalate pharmacist.  
- Prescribing chỉ qua clinic Diagnosis→Prescribing (ngoài chatbox).  

---

## Acceptance (ship checklist)

1. Intelligence lock respected (no NLP/LLM in code path).  
2. Chatbox menu 1/2/3 deterministic.  
3. Pharmacist human E2E + claim/complete.  
4. Doctor: book via form or fallback link.  
5. Medicine: ≤5 cards + add cart; CONSULT escalate.  
6. Authz: own sessions only; pharmacist queue only.  
7. `dat-thuoc` untouched behavior.  

---

## Future Notes (not phases)

- NLP intent, AI summarize for pharmacist, push queue notify, Firestore security rules + custom token, live doctor chat, Recommendation persistence.

---

## Implement order (when you say go)

1. `move_agent_to_root` → **Clinic-Oupharmacy-BE** → P0  
2. → **oupharmacy-store** → P1 → P2 (store half)  
3. → **Clinic-Oupharmacy-FE** → P2 (inbox)  
4. Store P3 → P4  

Không bắt đầu code cho đến khi bạn confirm **implement**.
