"""
Audit Product.category FK vs ProductCategory M2M parity.

Usage:
  python manage.py audit_product_categories
  python manage.py audit_product_categories --limit 20
  python manage.py audit_product_categories --fail-on-mismatch
"""

from django.core.management.base import BaseCommand

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import Product, ProductCategory


class Command(BaseCommand):
    help = "Report products where FK primary category lacks matching ProductCategory row."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max sample product ids to print per mismatch bucket (default 50).",
        )
        parser.add_argument(
            "--fail-on-mismatch",
            action="store_true",
            help="Exit with code 1 when fk_without_m2m count > 0 (for CI).",
        )

    def handle(self, *args, **options):
        using = STORE_DATABASE_ALIAS
        limit = max(0, options["limit"])
        fail_on_mismatch = options["fail_on_mismatch"]

        active_with_fk = Product.objects.using(using).filter(
            active=True, category_id__isnull=False
        )
        total_active_fk = active_with_fk.count()

        fk_without_m2m_ids = []
        for product in active_with_fk.only("id", "category_id").iterator(chunk_size=500):
            has_row = ProductCategory.objects.using(using).filter(
                product_id=product.id, category_id=product.category_id
            ).exists()
            if not has_row:
                fk_without_m2m_ids.append(product.id)

        m2m_primary_mismatch_ids = []
        primary_links = (
            ProductCategory.objects.using(using)
            .filter(is_primary=True)
            .select_related("product")
            .only("product_id", "category_id", "product__category_id", "product__active")
        )
        for link in primary_links.iterator(chunk_size=500):
            if not link.product.active:
                continue
            if link.product.category_id != link.category_id:
                m2m_primary_mismatch_ids.append(link.product_id)

        no_fk_no_m2m = (
            Product.objects.using(using)
            .filter(active=True, category_id__isnull=True)
            .exclude(
                id__in=ProductCategory.objects.using(using).values_list("product_id", flat=True)
            )
            .count()
        )

        self.stdout.write(f"Active products with category FK: {total_active_fk}")
        self.stdout.write(
            self.style.WARNING(
                f"FK without matching M2M row (same category_id): {len(fk_without_m2m_ids)}"
            )
        )
        self.stdout.write(
            f"Primary M2M category_id != Product.category_id: {len(m2m_primary_mismatch_ids)}"
        )
        self.stdout.write(f"Active products with no FK and no M2M: {no_fk_no_m2m}")

        if fk_without_m2m_ids and limit:
            self.stdout.write(f"Sample FK-without-M2M product ids: {fk_without_m2m_ids[:limit]}")
            self.stdout.write("Run: python manage.py backfill_product_categories")

        if m2m_primary_mismatch_ids and limit:
            sample = m2m_primary_mismatch_ids[:limit]
            self.stdout.write(f"Sample primary M2M/FK mismatch product ids: {sample}")

        if fail_on_mismatch and fk_without_m2m_ids:
            self.stderr.write(
                self.style.ERROR(
                    f"Audit failed: {len(fk_without_m2m_ids)} products missing ProductCategory rows."
                )
            )
            raise SystemExit(1)

        if not fk_without_m2m_ids and not m2m_primary_mismatch_ids:
            self.stdout.write(self.style.SUCCESS("Audit OK — FK/M2M primary alignment clean."))
