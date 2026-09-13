# ConsultationSession — pharmacist live-consult (messages in Firestore).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0023_medicine_request"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConsultationSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                ("user_id", models.BigIntegerField(db_column="user_id", db_index=True)),
                (
                    "pharmacist_id",
                    models.BigIntegerField(
                        blank=True,
                        db_column="pharmacist_id",
                        db_index=True,
                        null=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("WAITING_FOR_PROFESSIONAL", "Chờ dược sĩ"),
                            ("IN_PROGRESS", "Đang tư vấn"),
                            ("COMPLETED", "Hoàn thành"),
                            ("CANCELLED", "Đã hủy"),
                        ],
                        db_column="status",
                        db_index=True,
                        default="WAITING_FOR_PROFESSIONAL",
                        max_length=32,
                    ),
                ),
                (
                    "firestore_conversation_id",
                    models.CharField(
                        blank=True,
                        db_column="firestore_conversation_id",
                        default="",
                        max_length=128,
                    ),
                ),
                ("need_text", models.TextField(blank=True, db_column="need_text", default="")),
                (
                    "context_json",
                    models.JSONField(blank=True, db_column="context_json", default=dict),
                ),
            ],
            options={
                "verbose_name": "Consultation Session",
                "verbose_name_plural": "Consultation Sessions",
                "db_table": "store_consultation_session",
            },
        ),
        migrations.AddIndex(
            model_name="consultationsession",
            index=models.Index(fields=["user_id", "-created_date"], name="store_consu_user_id_833472_idx"),
        ),
        migrations.AddIndex(
            model_name="consultationsession",
            index=models.Index(fields=["status", "-created_date"], name="store_consu_status_2a7607_idx"),
        ),
        migrations.AddIndex(
            model_name="consultationsession",
            index=models.Index(fields=["pharmacist_id", "status"], name="store_consu_pharmac_bd1e9f_idx"),
        ),
    ]
