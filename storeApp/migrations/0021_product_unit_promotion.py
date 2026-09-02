# P1 — ProductUnitPromotion for catalog tier promos (D-PRC Option 1).

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0020_cabinet_alert"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductUnitPromotion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True, db_column="created_date")),
                ("updated_date", models.DateTimeField(auto_now=True, db_column="updated_date")),
                ("active", models.BooleanField(db_column="active", default=True)),
                ("source", models.CharField(db_column="source", default="hot_sale", max_length=32)),
                ("tier_percent", models.PositiveSmallIntegerField(db_column="tier_percent")),
                ("list_price", models.DecimalField(db_column="list_price", decimal_places=2, max_digits=12)),
                ("sale_price", models.DecimalField(db_column="sale_price", decimal_places=2, max_digits=12)),
                (
                    "previous_price_value",
                    models.DecimalField(db_column="previous_price_value", decimal_places=2, max_digits=12),
                ),
                (
                    "previous_compare_at_price",
                    models.DecimalField(
                        blank=True,
                        db_column="previous_compare_at_price",
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                    ),
                ),
                ("starts_at", models.DateTimeField(blank=True, db_column="starts_at", null=True)),
                ("ends_at", models.DateTimeField(blank=True, db_column="ends_at", null=True)),
                ("is_active", models.BooleanField(db_column="is_active", db_index=True, default=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        db_column="campaign_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="unit_promotions",
                        to="storeApp.campaign",
                    ),
                ),
                (
                    "product_variant_unit",
                    models.ForeignKey(
                        db_column="product_variant_unit_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="promotions",
                        to="storeApp.productvariantunit",
                    ),
                ),
            ],
            options={
                "db_table": "store_product_unit_promotion",
                "ordering": ["-id"],
            },
        ),
        migrations.AddIndex(
            model_name="productunitpromotion",
            index=models.Index(fields=["campaign", "is_active"], name="unit_promo_campaign_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="productunitpromotion",
            constraint=models.UniqueConstraint(
                fields=("campaign", "product_variant_unit"),
                name="unit_promo_campaign_unit_unique",
            ),
        ),
    ]
