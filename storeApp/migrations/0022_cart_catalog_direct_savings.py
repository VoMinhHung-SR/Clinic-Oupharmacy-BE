# P2 — Cart catalog direct savings snapshots (D-PRC-05).

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0021_product_unit_promotion"),
    ]

    operations = [
        migrations.AddField(
            model_name="cart",
            name="catalog_direct_savings_total",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Sum of (list_snapshot - sale_snapshot) x qty — informational (D-PRC-05)",
                max_digits=12,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="list_price_snapshot",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Compare-at / list at add-to-cart when above sale snapshot",
                max_digits=12,
                null=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="list_price_snapshot",
            field=models.DecimalField(
                blank=True,
                db_column="list_price_snapshot",
                decimal_places=2,
                max_digits=12,
                null=True,
                validators=[MinValueValidator(0)],
            ),
        ),
    ]
