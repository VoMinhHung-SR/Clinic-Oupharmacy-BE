# Generated migration - Populate slug for existing categories
from django.db import migrations
import re


def generate_slug_from_name(name):
    """Generate slug từ name"""
    from django.utils.text import slugify
    slug = slugify(name)
    if not slug:
        slug = name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
    return slug[:254]


def populate_category_slug(apps, schema_editor):
    """Populate slug cho existing categories"""
    Category = apps.get_model('mainApp', 'Category')
    
    for category in Category.objects.all().order_by('id'):
        if not category.slug:
            category.slug = generate_slug_from_name(category.name)
            category.save()


def reverse_populate_category_slug(apps, schema_editor):
    """Reverse migration - không cần làm gì"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('mainApp', '0009_alter_category_options_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_category_slug, reverse_populate_category_slug),
    ]

