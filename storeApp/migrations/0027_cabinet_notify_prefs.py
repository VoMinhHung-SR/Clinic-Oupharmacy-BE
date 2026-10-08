from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0026_cabinet_item_dose_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cabinet",
            name="reminder_enabled",
            field=models.BooleanField(db_column="reminder_enabled", default=False),
        ),
        migrations.AddField(
            model_name="cabinet",
            name="dose_reminder_enabled",
            field=models.BooleanField(db_column="dose_reminder_enabled", default=False),
        ),
    ]
