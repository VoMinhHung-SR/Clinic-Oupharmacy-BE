from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from mainApp.models import BaseModel

EXPIRING_SOON_DAYS = 30
EXPIRING_DAYS = 90

DEFAULT_CABINET_NAME = "Tủ thuốc gia đình"

EXPIRED = "EXPIRED"
EXPIRING_SOON = "EXPIRING_SOON"
EXPIRING = "EXPIRING"
SAFE = "SAFE"

IN_STOCK = "IN_STOCK"
LOW_STOCK = "LOW_STOCK"
OUT_OF_STOCK = "OUT_OF_STOCK"

DEFAULT_LOW_STOCK_THRESHOLD = 5


def expiration_status_for(expiration_date, today=None, soon_days=None):
    """Compute expiry bucket from a date. Not stored on the row."""
    if expiration_date is None:
        return SAFE
    today = today or timezone.now().date()
    soon = EXPIRING_SOON_DAYS if soon_days is None else int(soon_days)
    days = (expiration_date - today).days
    if days < 0:
        return EXPIRED
    if days < soon:
        return EXPIRING_SOON
    if days < EXPIRING_DAYS:
        return EXPIRING
    return SAFE


def days_until_expiry_for(expiration_date, today=None):
    if expiration_date is None:
        return None
    today = today or timezone.now().date()
    return (expiration_date - today).days


def expiration_date_range(status, today=None, soon_days=None):
    """Map a status filter to (gte, lt) dates. Exclusive upper bound."""
    today = today or timezone.now().date()
    soon = EXPIRING_SOON_DAYS if soon_days is None else int(soon_days)
    if status == EXPIRED:
        return None, today
    if status == EXPIRING_SOON:
        return today, today + timedelta(days=soon)
    if status == EXPIRING:
        return today + timedelta(days=soon), today + timedelta(days=EXPIRING_DAYS)
    if status == SAFE:
        return today + timedelta(days=EXPIRING_DAYS), None
    return None, None


class Cabinet(BaseModel):
    user_id = models.BigIntegerField(db_column="user_id", db_index=True)
    name = models.CharField(max_length=120, db_column="name")
    reminder_enabled = models.BooleanField(default=True, db_column="reminder_enabled")
    expiring_soon_days = models.PositiveIntegerField(
        default=EXPIRING_SOON_DAYS,
        db_column="expiring_soon_days",
        validators=[MinValueValidator(1), MaxValueValidator(365)],
    )

    class Meta:
        db_table = "store_cabinet"

    def __str__(self):
        return f"{self.name} ({self.user_id})"


class CabinetItem(BaseModel):
    cabinet = models.ForeignKey(
        Cabinet,
        on_delete=models.CASCADE,
        related_name="items",
        db_column="cabinet_id",
    )
    product_variant = models.ForeignKey(
        "ProductVariant",
        on_delete=models.PROTECT,
        related_name="cabinet_items",
        db_column="product_variant_id",
    )
    product_variant_unit = models.ForeignKey(
        "ProductVariantUnit",
        on_delete=models.PROTECT,
        related_name="cabinet_items",
        db_column="product_variant_unit_id",
    )
    quantity = models.IntegerField(
        db_column="quantity",
        validators=[MinValueValidator(0)],
    )
    expiration_date = models.DateField(db_column="expiration_date")
    lot_number = models.CharField(max_length=80, null=True, blank=True, db_column="lot_number")
    low_stock_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_column="low_stock_threshold",
        validators=[MinValueValidator(0)],
    )
    on_refill_list = models.BooleanField(default=False, db_column="on_refill_list")

    class Meta:
        db_table = "store_cabinet_item"
        indexes = [
            models.Index(fields=["cabinet", "expiration_date"]),
        ]

    def expiration_status(self, today=None):
        soon = getattr(self.cabinet, "expiring_soon_days", None) or EXPIRING_SOON_DAYS
        return expiration_status_for(self.expiration_date, today=today, soon_days=soon)

    def days_until_expiry(self, today=None):
        return days_until_expiry_for(self.expiration_date, today=today)

    def effective_low_stock_threshold(self):
        if self.low_stock_threshold is not None:
            return self.low_stock_threshold
        return DEFAULT_LOW_STOCK_THRESHOLD

    def inventory_status(self):
        if self.quantity <= 0:
            return OUT_OF_STOCK
        if self.quantity <= self.effective_low_stock_threshold():
            return LOW_STOCK
        return IN_STOCK


ALERT_EXPIRED = "EXPIRED"
ALERT_EXPIRING_SOON = "EXPIRING_SOON"

CABINET_ALERT_KIND_CHOICES = [
    (ALERT_EXPIRED, "Expired"),
    (ALERT_EXPIRING_SOON, "Expiring soon"),
]

DEFAULT_ALERT_DEDUPE_DAYS = 7


class CabinetAlert(BaseModel):
    """User-scoped cabinet HSD reminder. Not warehouse Notification / MedicineBatch."""

    user_id = models.BigIntegerField(db_column="user_id", db_index=True)
    cabinet_item = models.ForeignKey(
        CabinetItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
        db_column="cabinet_item_id",
    )
    kind = models.CharField(
        max_length=20,
        choices=CABINET_ALERT_KIND_CHOICES,
        db_column="kind",
    )
    title = models.CharField(max_length=255, db_column="title")
    body = models.TextField(db_column="body")
    is_read = models.BooleanField(default=False, db_column="is_read")
    read_at = models.DateTimeField(null=True, blank=True, db_column="read_at")

    class Meta:
        db_table = "store_cabinet_alert"
        indexes = [
            models.Index(fields=["user_id", "is_read"]),
            models.Index(fields=["cabinet_item", "kind", "created_date"]),
        ]

    def mark_as_read(self):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at", "updated_date"])

    def __str__(self):
        return f"{self.kind}: {self.title} ({self.user_id})"
