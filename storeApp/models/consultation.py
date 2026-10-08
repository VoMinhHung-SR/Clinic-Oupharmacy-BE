from django.db import models

from mainApp.models import BaseModel


class ConsultationSession(BaseModel):
    """Pharmacist live-consult session (storefront chat hub). Messages live in Firestore."""

    WAITING_FOR_PROFESSIONAL = "WAITING_FOR_PROFESSIONAL"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (WAITING_FOR_PROFESSIONAL, "Chờ dược sĩ"),
        (IN_PROGRESS, "Đang tư vấn"),
        (COMPLETED, "Hoàn thành"),
        (CANCELLED, "Đã hủy"),
    ]

    user_id = models.BigIntegerField(db_column="user_id", db_index=True)
    pharmacist_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_column="pharmacist_id",
        db_index=True,
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=WAITING_FOR_PROFESSIONAL,
        db_column="status",
        db_index=True,
    )
    firestore_conversation_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_column="firestore_conversation_id",
    )
    need_text = models.TextField(blank=True, default="", db_column="need_text")
    context_json = models.JSONField(default=dict, blank=True, db_column="context_json")

    class Meta:
        db_table = "store_consultation_session"
        verbose_name = "Consultation Session"
        verbose_name_plural = "Consultation Sessions"
        indexes = [
            models.Index(fields=["user_id", "-created_date"]),
            models.Index(fields=["status", "-created_date"]),
            models.Index(fields=["pharmacist_id", "status"]),
        ]

    def __str__(self):
        return f"ConsultationSession#{self.pk} user={self.user_id} [{self.status}]"
