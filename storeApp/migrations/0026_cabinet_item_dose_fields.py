from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0025_product_variant_preorder"),
    ]

    operations = [
        migrations.AddField(
            model_name="cabinetitem",
            name="dose_enabled",
            field=models.BooleanField(db_column="dose_enabled", default=False),
        ),
        migrations.AddField(
            model_name="cabinetitem",
            name="dose_times",
            field=models.JSONField(blank=True, db_column="dose_times", default=list),
        ),
        migrations.AddField(
            model_name="cabinetitem",
            name="dose_label",
            field=models.CharField(blank=True, db_column="dose_label", default="", max_length=80),
        ),
    ]
