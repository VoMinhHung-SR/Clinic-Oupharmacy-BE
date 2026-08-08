# Generated manually for P5-T2 Order.campaign_id attribution

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0015_campaign_voucher"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="campaign",
            field=models.ForeignKey(
                blank=True,
                db_column="campaign_id",
                help_text="Best-effort marketing attribution (D-10)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orders",
                to="storeApp.campaign",
            ),
        ),
    ]
