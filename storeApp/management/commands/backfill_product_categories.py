"""
Backfill ProductCategory M2M từ Product.category FK (primary).

Usage:
  python manage.py backfill_product_categories
  python manage.py backfill_product_categories --dry-run
"""

from django.core.management.base import BaseCommand

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import Product, ProductCategory


class Command(BaseCommand):
    help = "Copy Product.category_id → ProductCategory (is_primary=True) when missing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Chỉ in thống kê, không ghi DB.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        using = STORE_DATABASE_ALIAS
        created = 0
        skipped = 0
        synced_fk = 0

        qs = Product.objects.using(using).filter(category_id__isnull=False).order_by("id")
        total = qs.count()
        self.stdout.write(f"Products with category FK: {total}")

        for product in qs.iterator(chunk_size=500):
            has_link = ProductCategory.objects.using(using).filter(
                product=product, category_id=product.category_id
            ).exists()
            if has_link:
                skipped += 1
                continue
            if dry_run:
                created += 1
                continue

            has_primary = ProductCategory.objects.using(using).filter(
                product=product, is_primary=True
            ).exists()
            ProductCategory.objects.using(using).create(
                product=product,
                category_id=product.category_id,
                is_primary=not has_primary,
                sort_order=0,
            )
            created += 1

        without_primary = (
            Product.objects.using(using)
            .filter(category_id__isnull=False)
            .exclude(
                id__in=ProductCategory.objects.using(using)
                .filter(is_primary=True)
                .values_list("product_id", flat=True)
            )
        )
        for product in without_primary.iterator(chunk_size=500):
            if dry_run:
                synced_fk += 1
                continue
            pc = (
                ProductCategory.objects.using(using)
                .filter(product=product, category_id=product.category_id)
                .first()
            )
            if pc and not pc.is_primary:
                ProductCategory.objects.using(using).filter(product=product, is_primary=True).update(
                    is_primary=False
                )
                pc.is_primary = True
                pc.save(using=using, update_fields=["is_primary"])
                synced_fk += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY-RUN] ' if dry_run else ''}Created links: {created}, "
                f"already had row: {skipped}, primary sync fixes: {synced_fk}"
            )
        )
