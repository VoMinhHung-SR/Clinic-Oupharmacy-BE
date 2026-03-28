# Generated/edited manually for store-only migration.
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("mainApp", "0017_prescriptiondetail_item_name_snapshot_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="prescriptiondetail",
            name="medicine_unit",
        ),
        migrations.DeleteModel(
            name="MedicineUnitStats",
        ),
        migrations.DeleteModel(
            name="MedicineUnit",
        ),
        migrations.DeleteModel(
            name="Medicine",
        ),
        migrations.DeleteModel(
            name="Category",
        ),
    ]

