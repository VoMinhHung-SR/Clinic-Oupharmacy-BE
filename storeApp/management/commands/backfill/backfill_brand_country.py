"""
Backfill Brand.country from variant packing_meta.origin when empty.

Usage:
  python manage.py store_backfill brand-country --dry-run
  python manage.py store_backfill brand-country
  python manage.py store_backfill brand-country --database=store --limit=200
"""

from typing import Optional

from django.core.management.base import BaseCommand
from django.db.models import Q

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import Brand, ProductVariant
from storeApp.services.country_normalize import normalize_country_label
from storeApp.services.search_facets_service import SearchFacetsService


class Command(BaseCommand):
    help = "Backfill empty Brand.country from packing_meta.origin (canonical labels only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=STORE_DATABASE_ALIAS,
            help=f"Django DB alias (default: {STORE_DATABASE_ALIAS})",
        )
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit number of brands to process (0 = all).",
        )
        parser.add_argument(
            "--normalize-existing",
            action="store_true",
            help="Also rewrite non-canonical Brand.country values when normalizable.",
        )

    def handle(self, *args, **options):
        db = options["database"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        normalize_existing = options["normalize_existing"]

        brands = Brand.objects.using(db).filter(active=True).order_by("id")
        if not normalize_existing:
            brands = brands.filter(Q(country__isnull=True) | Q(country=""))
        brand_list = list(brands[:limit] if limit > 0 else brands)

        updated = 0
        skipped = 0
        unresolved = 0

        for brand in brand_list:
            current = (brand.country or "").strip()
            if current and not normalize_existing:
                skipped += 1
                continue

            canonical = normalize_country_label(current) if current else None
            if not canonical:
                origin = self._origin_from_brand_variants(brand.id, db)
                canonical = normalize_country_label(origin or "")

            if not canonical:
                unresolved += 1
                continue
            if current == canonical:
                skipped += 1
                continue

            self.stdout.write(f"Brand#{brand.id} {brand.name!r}: {current!r} -> {canonical!r}")
            if not dry_run:
                Brand.objects.using(db).filter(pk=brand.pk).update(country=canonical)
            updated += 1

        if updated and not dry_run:
            SearchFacetsService.invalidate_all_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f"brand-country backfill done: updated={updated} skipped={skipped} "
                f"unresolved={unresolved} dry_run={dry_run}"
            )
        )

    @staticmethod
    def _origin_from_brand_variants(brand_id: int, db: str) -> Optional[str]:
        variants = (
            ProductVariant.objects.using(db)
            .filter(product__brand_id=brand_id)
            .exclude(packing_meta={})
            .values_list("packing_meta", flat=True)[:50]
        )
        for meta in variants:
            if not isinstance(meta, dict):
                continue
            origin = str(meta.get("origin") or "").strip()
            if origin:
                return origin
        return None
