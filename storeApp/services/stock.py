"""
Stock service: single source of truth = Batches (store DB).
- get_available_stock(medicine_unit_id)
- deduct_stock(medicine_unit_id, quantity)  # FIFO on batches, then sync cache
- restore_stock(medicine_unit_id, quantity)  # LIFO restore into nearest-expiry batch or create ADJ batch
- sync_in_stock_cache(medicine_unit_id)      # Update MedicineUnit.in_stock from batch sum
"""
from django.db import transaction, models
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from mainApp.models import MedicineUnit
from storeApp.models import MedicineBatch


def get_available_stock(medicine_unit_id):
    """
    Sum remaining_quantity from Batches (store): active, remaining_quantity > 0, expiry_date >= today.
    Fallback: if no such batches, return MedicineUnit.in_stock (default DB).
    """
    today = timezone.now().date()
    total = (
        MedicineBatch.objects.using('store')
        .filter(
            medicine_unit_id=medicine_unit_id,
            active=True,
            remaining_quantity__gt=0,
            expiry_date__gte=today,
        )
        .aggregate(total=models.Sum('remaining_quantity'))['total']
    )
    if total is not None:
        return int(total)
    try:
        unit = MedicineUnit.objects.using('default').get(id=medicine_unit_id)
        return getattr(unit, 'in_stock', 0) or 0
    except MedicineUnit.DoesNotExist:
        return 0


def deduct_stock(medicine_unit_id, quantity):
    """
    Deduct quantity from batches (store) FIFO. Raise ValueError if insufficient.
    Then sync MedicineUnit.in_stock cache (default DB).
    """
    if quantity <= 0:
        return
    today = timezone.now().date()
    batches = list(
        MedicineBatch.objects.using('store')
        .filter(
            medicine_unit_id=medicine_unit_id,
            active=True,
            remaining_quantity__gt=0,
            expiry_date__gte=today,
        )
        .order_by('expiry_date', 'import_date')
    )
    remaining = quantity
    for batch in batches:
        if remaining <= 0:
            break
        if batch.remaining_quantity >= remaining:
            batch.remaining_quantity -= remaining
            batch.save(update_fields=['remaining_quantity'])
            remaining = 0
        else:
            remaining -= batch.remaining_quantity
            batch.remaining_quantity = 0
            batch.save(update_fields=['remaining_quantity'])
    if remaining > 0:
        raise ValueError(
            f'Insufficient stock for medicine_unit_id {medicine_unit_id}. Could not deduct {remaining} units.'
        )
    sync_in_stock_cache(medicine_unit_id)


def restore_stock(medicine_unit_id, quantity):
    """
    Restore quantity: add to the batch with nearest expiry (LIFO restore).
    If no suitable batch, create an adjustment batch (ADJ-{unit_id}-{timestamp}).
    Then sync MedicineUnit.in_stock cache.
    """
    if quantity <= 0:
        return
    today = timezone.now().date()
    batches = list(
        MedicineBatch.objects.using('store')
        .filter(
            medicine_unit_id=medicine_unit_id,
            active=True,
            expiry_date__gte=today,
        )
        .order_by('expiry_date', 'import_date')
    )
    if batches:
        # LIFO restore: add to batch with nearest expiry (first in FIFO order = soonest to expire)
        batch = batches[0]
        batch.remaining_quantity += quantity
        batch.save(update_fields=['remaining_quantity'])
    else:
        # No batch to restore into: create adjustment batch
        ts = timezone.now().strftime('%Y%m%d%H%M%S')
        batch_number = f'ADJ-{medicine_unit_id}-{ts}'
        expiry_date = today + relativedelta(months=12)
        MedicineBatch.objects.using('store').create(
            batch_number=batch_number,
            medicine_unit_id=medicine_unit_id,
            import_date=today,
            expiry_date=expiry_date,
            quantity=quantity,
            remaining_quantity=quantity,
            import_price=None,
            active=True,
        )
    sync_in_stock_cache(medicine_unit_id)


def sync_in_stock_cache(medicine_unit_id):
    """
    Set MedicineUnit.in_stock (default DB) to sum of remaining_quantity from Batches (store)
    where active, remaining_quantity > 0, expiry_date >= today.
    """
    today = timezone.now().date()
    total = (
        MedicineBatch.objects.using('store')
        .filter(
            medicine_unit_id=medicine_unit_id,
            active=True,
            remaining_quantity__gt=0,
            expiry_date__gte=today,
        )
        .aggregate(total=models.Sum('remaining_quantity'))['total']
    )
    value = int(total) if total is not None else 0
    MedicineUnit.objects.using('default').filter(id=medicine_unit_id).update(in_stock=value)