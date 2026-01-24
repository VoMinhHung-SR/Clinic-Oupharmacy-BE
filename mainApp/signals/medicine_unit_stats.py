"""
Signal handlers for MedicineUnit model
Auto-create MedicineUnitStats when MedicineUnit is created
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from mainApp.models import MedicineUnit, MedicineUnitStats


@receiver(post_save, sender=MedicineUnit)
def ensure_medicine_unit_stats(sender, instance, **kwargs):
    """
    Ensure MedicineUnitStats exists for every MedicineUnit.
    Safe for create, update, and recovery cases.
    """
    MedicineUnitStats.objects.get_or_create(unit=instance)
