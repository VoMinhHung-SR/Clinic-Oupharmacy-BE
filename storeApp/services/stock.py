"""
Stock service (store DB).
Primary: MedicineBatch FIFO when batch inventory is available.
Fallback: ProductVariant.in_stock cache when batches are empty or schema is legacy.
"""
import logging

from dateutil.relativedelta import relativedelta
from django.db import models
from django.db.utils import DatabaseError, ProgrammingError
from django.utils import timezone

from storeApp.models import MedicineBatch, ProductVariant

logger = logging.getLogger(__name__)


def _get_cache_stock(product_variant_id: int) -> int:
    value = (
        ProductVariant.objects.using("store")
        .filter(id=product_variant_id, active=True)
        .values_list("in_stock", flat=True)
        .first()
    )
    return int(value or 0)


def _sum_batch_stock(product_variant_id: int) -> int | None:
    """
    Sum batch remaining_quantity for variant.
    Returns None when batch inventory is unavailable (schema drift / query error).
    """
    today = timezone.now().date()
    try:
        total = (
            MedicineBatch.objects.using("store")
            .filter(
                product_variant_id=product_variant_id,
                active=True,
                remaining_quantity__gt=0,
                expiry_date__gte=today,
            )
            .aggregate(total=models.Sum("remaining_quantity"))["total"]
        )
    except (ProgrammingError, DatabaseError) as exc:
        logger.warning(
            "MedicineBatch stock query failed for variant %s; using in_stock cache (%s)",
            product_variant_id,
            exc,
        )
        return None
    return int(total) if total is not None else 0


def _list_deductible_batches(product_variant_id: int) -> list[MedicineBatch] | None:
    today = timezone.now().date()
    try:
        return list(
            MedicineBatch.objects.using("store")
            .filter(
                product_variant_id=product_variant_id,
                active=True,
                remaining_quantity__gt=0,
                expiry_date__gte=today,
            )
            .order_by("expiry_date", "import_date")
        )
    except (ProgrammingError, DatabaseError) as exc:
        logger.warning(
            "MedicineBatch list failed for variant %s; using in_stock cache (%s)",
            product_variant_id,
            exc,
        )
        return None


def _deduct_cache_stock(product_variant_id: int, quantity: int) -> None:
    if quantity <= 0:
        return
    updated = (
        ProductVariant.objects.using("store")
        .filter(id=product_variant_id, active=True, in_stock__gte=quantity)
        .update(in_stock=models.F("in_stock") - quantity)
    )
    if not updated:
        raise ValueError(
            f"Insufficient stock for product_variant_id {product_variant_id}. "
            f"Could not deduct {quantity} base unit(s) from cache."
        )


def get_available_stock(product_variant_id):
    """
    Available base units for a variant.
    Prefer batch sum when batch inventory exists; otherwise use ProductVariant.in_stock cache.
    """
    batch_total = _sum_batch_stock(product_variant_id)
    if batch_total is not None and batch_total > 0:
        return batch_total
    return _get_cache_stock(product_variant_id)


def deduct_stock(product_variant_id, quantity):
    """
    Deduct base units: FIFO on batches when available, else decrement in_stock cache.
    """
    if quantity <= 0:
        return

    batches = _list_deductible_batches(product_variant_id)
    if batches is None:
        _deduct_cache_stock(product_variant_id, quantity)
        return

    if not batches:
        _deduct_cache_stock(product_variant_id, quantity)
        return

    remaining = quantity
    for batch in batches:
        if remaining <= 0:
            break
        if batch.remaining_quantity >= remaining:
            batch.remaining_quantity -= remaining
            batch.save(update_fields=["remaining_quantity"])
            remaining = 0
        else:
            remaining -= batch.remaining_quantity
            batch.remaining_quantity = 0
            batch.save(update_fields=["remaining_quantity"])

    if remaining > 0:
        raise ValueError(
            f"Insufficient stock for product_variant_id {product_variant_id}. "
            f"Could not deduct {remaining} of {quantity} base unit(s)."
        )
    sync_in_stock_cache(product_variant_id)


def restore_stock(product_variant_id, quantity):
    """
    Restore quantity: add to nearest-expiry batch, or create ADJ batch, or bump cache.
    """
    if quantity <= 0:
        return

    today = timezone.now().date()
    try:
        batches = list(
            MedicineBatch.objects.using("store")
            .filter(
                product_variant_id=product_variant_id,
                active=True,
                expiry_date__gte=today,
            )
            .order_by("expiry_date", "import_date")
        )
    except (ProgrammingError, DatabaseError) as exc:
        logger.warning(
            "MedicineBatch restore list failed for variant %s; bumping cache (%s)",
            product_variant_id,
            exc,
        )
        ProductVariant.objects.using("store").filter(id=product_variant_id).update(
            in_stock=models.F("in_stock") + quantity
        )
        return

    if batches:
        batch = batches[0]
        batch.remaining_quantity += quantity
        batch.save(update_fields=["remaining_quantity"])
    else:
        ts = timezone.now().strftime("%Y%m%d%H%M%S")
        batch_number = f"ADJ-{product_variant_id}-{ts}"
        expiry_date = today + relativedelta(months=12)
        try:
            MedicineBatch.objects.using("store").create(
                batch_number=batch_number,
                product_variant_id=product_variant_id,
                import_date=today,
                expiry_date=expiry_date,
                quantity=quantity,
                remaining_quantity=quantity,
                import_price_per_base_unit=None,
                active=True,
            )
        except (ProgrammingError, DatabaseError):
            ProductVariant.objects.using("store").filter(id=product_variant_id).update(
                in_stock=models.F("in_stock") + quantity
            )
            return

    sync_in_stock_cache(product_variant_id)


def sync_in_stock_cache(product_variant_id):
    """Set ProductVariant.in_stock from batch sum when batches are available."""
    batch_total = _sum_batch_stock(product_variant_id)
    if batch_total is None:
        return
    ProductVariant.objects.using("store").filter(id=product_variant_id).update(in_stock=batch_total)
