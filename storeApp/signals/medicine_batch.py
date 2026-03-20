"""
Signals for storeApp: sync MedicineUnit.in_stock cache when MedicineBatch changes.
"""
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from storeApp.models import MedicineBatch
from storeApp.services.stock import sync_in_stock_cache


@receiver(pre_save, sender=MedicineBatch)
def medicine_batch_pre_save(sender, instance, **kwargs):
    """Store old product_variant_id on update so we can sync both variants in post_save."""
    if instance.pk:
        try:
            old = MedicineBatch.objects.using('store').get(pk=instance.pk)
            instance._old_product_variant_id = old.product_variant_id
        except MedicineBatch.DoesNotExist:
            pass


@receiver(post_save, sender=MedicineBatch)
def medicine_batch_post_save(sender, instance, created, **kwargs):
    """Sync cache for the variant linked to this batch. On update, sync old variant if product_variant_id changed."""
    if instance.product_variant_id:
        sync_in_stock_cache(instance.product_variant_id)
    
    old_variant_id = getattr(instance, '_old_product_variant_id', None)
    if not created and old_variant_id is not None:
        if old_variant_id != instance.product_variant_id:
            sync_in_stock_cache(old_variant_id)


@receiver(post_delete, sender=MedicineBatch)
def medicine_batch_post_delete(sender, instance, **kwargs):
    """Sync cache for the variant that had this batch."""
    if instance.product_variant_id:
        sync_in_stock_cache(instance.product_variant_id)
