# Ensure UserRole ROLE_PHARMACIST exists (Consultation Hub).

from django.db import migrations


def seed_role_pharmacist(apps, schema_editor):
    UserRole = apps.get_model("mainApp", "UserRole")
    UserRole.objects.get_or_create(name="ROLE_PHARMACIST", defaults={"active": True})


def unseed_role_pharmacist(apps, schema_editor):
    UserRole = apps.get_model("mainApp", "UserRole")
    UserRole.objects.filter(name="ROLE_PHARMACIST").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mainApp", "0021_visit_model_status_constraints_bill_allergies"),
    ]

    operations = [
        migrations.RunPython(seed_role_pharmacist, unseed_role_pharmacist),
    ]
