from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models.consultation import ConsultationSession


def waiting_queryset():
    return (
        ConsultationSession.objects.filter(
            active=True,
            status=ConsultationSession.WAITING_FOR_PROFESSIONAL,
            pharmacist_id__isnull=True,
        )
        .order_by("created_date", "id")
    )


def claim_session(*, session_id: int, pharmacist_id: int) -> ConsultationSession:
    """Atomically assign a waiting session to a pharmacist."""
    with transaction.atomic(using=STORE_DATABASE_ALIAS):
        try:
            session = (
                ConsultationSession.objects.select_for_update()
                .using(STORE_DATABASE_ALIAS)
                .get(pk=session_id, active=True)
            )
        except ConsultationSession.DoesNotExist as exc:
            raise ValidationError({"detail": "Session không tồn tại."}) from exc

        if session.status != ConsultationSession.WAITING_FOR_PROFESSIONAL:
            raise ValidationError({"detail": "Session không còn trong hàng chờ."})
        if session.pharmacist_id is not None:
            raise ValidationError({"detail": "Session đã được nhận bởi dược sĩ khác."})

        session.pharmacist_id = pharmacist_id
        session.status = ConsultationSession.IN_PROGRESS
        session.updated_date = timezone.now()
        session.save(update_fields=["pharmacist_id", "status", "updated_date"])
        return session


def assert_owner_or_assigned(*, session: ConsultationSession, user_id: int, is_pharmacist: bool):
    if session.user_id == user_id:
        return
    if is_pharmacist and session.pharmacist_id == user_id:
        return
    raise PermissionDenied("Không có quyền truy cập session này.")
