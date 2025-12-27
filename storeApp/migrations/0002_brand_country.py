# Generated manually to add country field to Brand
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storeApp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='brand',
            name='country',
            field=models.CharField(blank=True, help_text='Quốc gia của thương hiệu (để filter)', max_length=100, null=True),
        ),
        migrations.AddIndex(
            model_name='brand',
            index=models.Index(fields=['country', 'active'], name='store_brand_country_active_idx'),
        ),
    ]

