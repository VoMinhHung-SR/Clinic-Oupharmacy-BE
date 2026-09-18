from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models.consultation import ConsultationSession

OPEN_STATUSES = (
    ConsultationSession.WAITING_FOR_PROFESSIONAL,
    ConsultationSession.IN_PROGRESS,
)


def get_or_create_open_session(
    *,
    user_id: int,
    need_text: str = "",
    context_json: dict | None = None,
    firestore_conversation_id: str = "",
) -> tuple[ConsultationSession, bool]:
    """
    Return the customer's open session if one exists; otherwise create.

    Returns (session, created). Merges non-empty need_text and context_json into
    an existing open session (escalate / reopen).
    """
    need = (need_text or "").strip()
    context = context_json or {}
    fs_id = (firestore_conversation_id or "").strip()

    with transaction.atomic(using=STORE_DATABASE_ALIAS):
        existing = (
            ConsultationSession.objects.select_for_update()
            .using(STORE_DATABASE_ALIAS)
            .filter(active=True, user_id=user_id, status__in=OPEN_STATUSES)
            .order_by("-created_date", "-id")
            .first()
        )
        if existing is None:
            session = ConsultationSession.objects.using(STORE_DATABASE_ALIAS).create(
                user_id=user_id,
                status=ConsultationSession.WAITING_FOR_PROFESSIONAL,
                need_text=need,
                context_json=context,
                firestore_conversation_id=fs_id,
            )
            return session, True

        update_fields: list[str] = []
        if need:
            existing.need_text = need
            update_fields.append("need_text")
        if context:
            merged = dict(existing.context_json or {})
            merged.update(context)
            existing.context_json = merged
            update_fields.append("context_json")
        if fs_id and not (existing.firestore_conversation_id or "").strip():
            existing.firestore_conversation_id = fs_id
            update_fields.append("firestore_conversation_id")
        if update_fields:
            existing.updated_date = timezone.now()
            update_fields.append("updated_date")
            existing.save(update_fields=update_fields)
        return existing, False
