# Generated by Django 4.2.21 on 2025-05-16 09:52

import cloudinary.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mainApp', '0002_alter_examination_time_slot'),
    ]

    operations = [
        migrations.AlterField(
            model_name='medicineunit',
            name='image',
            field=cloudinary.models.CloudinaryField(default='', max_length=255, null=True, verbose_name='medicines'),
        ),
    ]
