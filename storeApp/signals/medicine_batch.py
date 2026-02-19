"""
Signals for storeApp: sync MedicineUnit.in_stock cache when MedicineBatch changes.
"""
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from storeApp.models import MedicineBatch
from storeApp.services.stock import sync_in_stock_cache


@receiver(pre_save, sender=MedicineBatch)
def medicine_batch_pre_save(sender, instance, **kwargs):
    """Store old medicine_unit_id on update so we can sync both units in post_save."""
    if instance.pk:
        try:
            old = MedicineBatch.objects.using('store').get(pk=instance.pk)
            instance._old_medicine_unit_id = old.medicine_unit_id
        except MedicineBatch.DoesNotExist:
            pass


@receiver(post_save, sender=MedicineBatch)
def medicine_batch_post_save(sender, instance, created, **kwargs):
    """Sync cache for the unit linked to this batch. On update, sync old unit if medicine_unit_id changed."""
    sync_in_stock_cache(instance.medicine_unit_id)
    if not created and getattr(instance, '_old_medicine_unit_id', None) is not None:
        if instance._old_medicine_unit_id != instance.medicine_unit_id:
            sync_in_stock_cache(instance._old_medicine_unit_id)


@receiver(post_delete, sender=MedicineBatch)
def medicine_batch_post_delete(sender, instance, **kwargs):
    """Sync cache for the unit that had this batch."""
    sync_in_stock_cache(instance.medicine_unit_id)
