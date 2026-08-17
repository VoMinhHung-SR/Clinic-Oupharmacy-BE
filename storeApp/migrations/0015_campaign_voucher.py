# Generated manually for P5-T1 CampaignVoucher

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0014_campaign_product_and_category"),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignVoucher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                ("sort_order", models.IntegerField(db_column="sort_order", default=0)),
                ("is_featured", models.BooleanField(db_column="is_featured", default=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        db_column="campaign_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="voucher_links",
                        to="storeApp.campaign",
                    ),
                ),
                (
                    "voucher",
                    models.ForeignKey(
                        db_column="voucher_id",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="campaign_links",
                        to="storeApp.voucher",
                    ),
                ),
            ],
            options={
                "db_table": "store_campaign_voucher",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="campaignvoucher",
            constraint=models.UniqueConstraint(
                fields=("campaign", "voucher"),
                name="campaign_voucher_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="campaignvoucher",
            index=models.Index(fields=["campaign", "sort_order"], name="campaign_voucher_sort_idx"),
        ),
    ]
