# Generated for Smart Medicine Cabinet P2.

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0018_cabinet_and_cabinet_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="cabinet",
            name="reminder_enabled",
            field=models.BooleanField(db_column="reminder_enabled", default=True),
        ),
        migrations.AddField(
            model_name="cabinet",
            name="expiring_soon_days",
            field=models.PositiveIntegerField(
                db_column="expiring_soon_days",
                default=30,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(365),
                ],
            ),
        ),
        migrations.AddField(
            model_name="cabinetitem",
            name="lot_number",
            field=models.CharField(blank=True, db_column="lot_number", max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="cabinetitem",
            name="low_stock_threshold",
            field=models.PositiveIntegerField(
                blank=True,
                db_column="low_stock_threshold",
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="cabinetitem",
            name="on_refill_list",
            field=models.BooleanField(db_column="on_refill_list", default=False),
        ),
    ]
