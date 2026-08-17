from datetime import timedelta

from django.core.validators import MinValueValidator
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
OUT_OF_STOCK = "OUT_OF_STOCK"


def expiration_status_for(expiration_date, today=None):
    """Compute expiry bucket from a date. Not stored on the row."""
    if expiration_date is None:
        return SAFE
    today = today or timezone.now().date()
    days = (expiration_date - today).days
    if days < 0:
        return EXPIRED
    if days < EXPIRING_SOON_DAYS:
        return EXPIRING_SOON
    if days < EXPIRING_DAYS:
        return EXPIRING
    return SAFE


def days_until_expiry_for(expiration_date, today=None):
    if expiration_date is None:
        return None
    today = today or timezone.now().date()
    return (expiration_date - today).days


def expiration_date_range(status, today=None):
    """Map a status filter to (gte, lt) dates. Exclusive upper bound."""
    today = today or timezone.now().date()
    if status == EXPIRED:
        return None, today
    if status == EXPIRING_SOON:
        return today, today + timedelta(days=EXPIRING_SOON_DAYS)
    if status == EXPIRING:
        return today + timedelta(days=EXPIRING_SOON_DAYS), today + timedelta(days=EXPIRING_DAYS)
    if status == SAFE:
        return today + timedelta(days=EXPIRING_DAYS), None
    return None, None


class Cabinet(BaseModel):
    user_id = models.BigIntegerField(db_column="user_id", db_index=True)
    name = models.CharField(max_length=120, db_column="name")

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

    class Meta:
        db_table = "store_cabinet_item"
        indexes = [
            models.Index(fields=["cabinet", "expiration_date"]),
        ]

    def expiration_status(self, today=None):
        return expiration_status_for(self.expiration_date, today=today)

    def days_until_expiry(self, today=None):
        return days_until_expiry_for(self.expiration_date, today=today)

    def inventory_status(self):
        if self.quantity <= 0:
            return OUT_OF_STOCK
        return IN_STOCK
