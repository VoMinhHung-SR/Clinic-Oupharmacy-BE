# Generated manually for P4-T1 CampaignProduct + CampaignCategory

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0013_campaign_and_placement"),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                ("product_mid", models.CharField(db_column="product_mid", max_length=64)),
                ("sort_order", models.IntegerField(db_column="sort_order", default=0)),
                (
                    "campaign",
                    models.ForeignKey(
                        db_column="campaign_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="products",
                        to="storeApp.campaign",
                    ),
                ),
            ],
            options={
                "db_table": "store_campaign_product",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="CampaignCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                ("category_slug", models.CharField(db_column="category_slug", max_length=120)),
                ("sort_order", models.IntegerField(db_column="sort_order", default=0)),
                (
                    "campaign",
                    models.ForeignKey(
                        db_column="campaign_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="categories",
                        to="storeApp.campaign",
                    ),
                ),
            ],
            options={
                "db_table": "store_campaign_category",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="campaignproduct",
            constraint=models.UniqueConstraint(
                fields=("campaign", "product_mid"),
                name="campaign_product_mid_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="campaignproduct",
            index=models.Index(fields=["campaign", "sort_order"], name="campaign_product_sort_idx"),
        ),
        migrations.AddConstraint(
            model_name="campaigncategory",
            constraint=models.UniqueConstraint(
                fields=("campaign", "category_slug"),
                name="campaign_category_slug_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="campaigncategory",
            index=models.Index(fields=["campaign", "sort_order"], name="campaign_category_sort_idx"),
        ),
    ]
