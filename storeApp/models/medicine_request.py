from cloudinary.models import CloudinaryField
from django.db import models

from mainApp.models import BaseModel


class MedicineRequest(BaseModel):
    """Storefront medicine consult lead (Cần mua thuốc). Owner via user_id; ops status in admin."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    CONTACTED = "CONTACTED"
    CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (PENDING, "Chờ xử lý"),
        (IN_PROGRESS, "Đang xử lý"),
        (CONTACTED, "Đã liên hệ"),
        (CLOSED, "Đã đóng"),
    ]

    user_id = models.BigIntegerField(null=True, blank=True, db_column="user_id", db_index=True)
    full_name = models.CharField(max_length=120, db_column="full_name")
    phone = models.CharField(max_length=20, db_column="phone")
    email = models.EmailField(max_length=254, blank=True, default="", db_column="email")
    note = models.TextField(blank=True, default="", db_column="note")
    items_json = models.JSONField(default=list, blank=True, db_column="items_json")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=PENDING,
        db_column="status",
        db_index=True,
    )
    prescription_image = CloudinaryField(
        "medicine_requests",
        folder="OUPharmacy/medicine-requests",
        null=True,
        blank=True,
        default="",
    )

    class Meta:
        db_table = "store_medicine_request"
        verbose_name = "Medicine Request"
        verbose_name_plural = "Medicine Requests"
        indexes = [
            models.Index(fields=["user_id", "-created_date"]),
            models.Index(fields=["status", "-created_date"]),
        ]

    def __str__(self):
        return f"#{self.pk} {self.full_name} ({self.phone}) [{self.status}]"
