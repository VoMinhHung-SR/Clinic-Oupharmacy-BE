# Generated for Smart Cabinet Track A — user-scoped HSD alerts.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0019_cabinet_p2_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="CabinetAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                ("user_id", models.BigIntegerField(db_column="user_id", db_index=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[("EXPIRED", "Expired"), ("EXPIRING_SOON", "Expiring soon")],
                        db_column="kind",
                        max_length=20,
                    ),
                ),
                ("title", models.CharField(db_column="title", max_length=255)),
                ("body", models.TextField(db_column="body")),
                ("is_read", models.BooleanField(db_column="is_read", default=False)),
                ("read_at", models.DateTimeField(blank=True, db_column="read_at", null=True)),
                (
                    "cabinet_item",
                    models.ForeignKey(
                        blank=True,
                        db_column="cabinet_item_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alerts",
                        to="storeApp.cabinetitem",
                    ),
                ),
            ],
            options={
                "db_table": "store_cabinet_alert",
            },
        ),
        migrations.AddIndex(
            model_name="cabinetalert",
            index=models.Index(fields=["user_id", "is_read"], name="store_cabin_user_id_is_read_idx"),
        ),
        migrations.AddIndex(
            model_name="cabinetalert",
            index=models.Index(
                fields=["cabinet_item", "kind", "created_date"],
                name="store_cabin_item_kind_created_idx",
            ),
        ),
    ]
