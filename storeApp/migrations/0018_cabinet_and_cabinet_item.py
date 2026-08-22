# Generated for Smart Medicine Cabinet P1.

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0017_campaign_placement_slot_taxonomy_p9"),
    ]

    operations = [
        migrations.CreateModel(
            name="Cabinet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                ("user_id", models.BigIntegerField(db_column="user_id", db_index=True)),
                ("name", models.CharField(db_column="name", max_length=120)),
            ],
            options={
                "db_table": "store_cabinet",
            },
        ),
        migrations.CreateModel(
            name="CabinetItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                (
                    "quantity",
                    models.IntegerField(db_column="quantity", validators=[django.core.validators.MinValueValidator(0)]),
                ),
                ("expiration_date", models.DateField(db_column="expiration_date")),
                (
                    "cabinet",
                    models.ForeignKey(
                        db_column="cabinet_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="storeApp.cabinet",
                    ),
                ),
                (
                    "product_variant",
                    models.ForeignKey(
                        db_column="product_variant_id",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cabinet_items",
                        to="storeApp.productvariant",
                    ),
                ),
                (
                    "product_variant_unit",
                    models.ForeignKey(
                        db_column="product_variant_unit_id",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cabinet_items",
                        to="storeApp.productvariantunit",
                    ),
                ),
            ],
            options={
                "db_table": "store_cabinet_item",
            },
        ),
        migrations.AddIndex(
            model_name="cabinetitem",
            index=models.Index(fields=["cabinet", "expiration_date"], name="store_citem_cab_exp_idx"),
        ),
    ]
