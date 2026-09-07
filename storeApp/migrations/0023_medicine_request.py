# MedicineRequest lead model (P1 image + P2 history).

import cloudinary.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0022_cart_catalog_direct_savings"),
    ]

    operations = [
        migrations.CreateModel(
            name="MedicineRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                ("user_id", models.BigIntegerField(blank=True, db_column="user_id", db_index=True, null=True)),
                ("full_name", models.CharField(db_column="full_name", max_length=120)),
                ("phone", models.CharField(db_column="phone", max_length=20)),
                ("email", models.EmailField(blank=True, db_column="email", default="", max_length=254)),
                ("note", models.TextField(blank=True, db_column="note", default="")),
                ("items_json", models.JSONField(blank=True, db_column="items_json", default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Chờ xử lý"),
                            ("IN_PROGRESS", "Đang xử lý"),
                            ("CONTACTED", "Đã liên hệ"),
                            ("CLOSED", "Đã đóng"),
                        ],
                        db_column="status",
                        db_index=True,
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "prescription_image",
                    cloudinary.models.CloudinaryField(
                        blank=True,
                        default="",
                        max_length=255,
                        null=True,
                        verbose_name="medicine_requests",
                    ),
                ),
            ],
            options={
                "verbose_name": "Medicine Request",
                "verbose_name_plural": "Medicine Requests",
                "db_table": "store_medicine_request",
            },
        ),
        migrations.AddIndex(
            model_name="medicinerequest",
            index=models.Index(fields=["user_id", "-created_date"], name="store_medic_user_id_8713b9_idx"),
        ),
        migrations.AddIndex(
            model_name="medicinerequest",
            index=models.Index(fields=["status", "-created_date"], name="store_medic_status_98a281_idx"),
        ),
    ]
