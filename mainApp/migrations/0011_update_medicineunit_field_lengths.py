# Generated manually to update MedicineUnit field lengths
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mainApp', '0010_populate_category_slug'),
    ]

    operations = [
        # Change manufacturer from CharField(200) to TextField
        migrations.AlterField(
            model_name='medicineunit',
            name='manufacturer',
            field=models.TextField(blank=True, help_text='specifications.manufacturer - Nhà sản xuất (TextField để lưu trữ đầy đủ)', null=True),
        ),
        # Increase origin from 100 to 200
        migrations.AlterField(
            model_name='medicineunit',
            name='origin',
            field=models.CharField(blank=True, help_text='specifications.origin - Xuất xứ', max_length=200, null=True),
        ),
        # Increase shelf_life from 50 to 100
        migrations.AlterField(
            model_name='medicineunit',
            name='shelf_life',
            field=models.CharField(blank=True, help_text='specifications.shelfLife - Hạn sử dụng', max_length=100, null=True),
        ),
    ]


