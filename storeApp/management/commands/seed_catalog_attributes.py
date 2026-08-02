"""
Seed / upsert provisional CatalogAttribute (+ default options).

Usage:
  python manage.py seed_catalog_attributes
  python manage.py seed_catalog_attributes --database=store --dry-run
"""

from django.core.management.base import BaseCommand

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import CatalogAttribute, CatalogAttributeOption
from storeApp.services.catalog_attribute_seed import CATALOG_ATTRIBUTE_SEED


class Command(BaseCommand):
    help = "Upsert provisional catalog attribute dictionary for storefront facets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=STORE_DATABASE_ALIAS,
            help=f"Django DB alias (default: {STORE_DATABASE_ALIAS})",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        db = options["database"]
        dry_run = options["dry_run"]
        created_attrs = 0
        updated_attrs = 0
        created_options = 0

        for code, label, facet_type, sort_order, options_list in CATALOG_ATTRIBUTE_SEED:
            existing = (
                CatalogAttribute.objects.using(db).filter(code=code).first()
            )
            if existing is None:
                created_attrs += 1
                self.stdout.write(f"+ attribute {code}")
                if not dry_run:
                    attr = CatalogAttribute.objects.using(db).create(
                        code=code,
                        label=label,
                        facet_type=facet_type,
                        sort_order=sort_order,
                        is_filterable=True,
                        active=True,
                    )
                else:
                    attr = None
            else:
                attr = existing
                dirty = (
                    existing.label != label
                    or existing.facet_type != facet_type
                    or existing.sort_order != sort_order
                )
                if dirty:
                    updated_attrs += 1
                    self.stdout.write(f"~ attribute {code}")
                    if not dry_run:
                        existing.label = label
                        existing.facet_type = facet_type
                        existing.sort_order = sort_order
                        existing.save(
                            using=db,
                            update_fields=["label", "facet_type", "sort_order", "updated_date"],
                        )

            if attr is None:
                continue

            for opt_slug, opt_label in options_list:
                opt_exists = (
                    CatalogAttributeOption.objects.using(db)
                    .filter(attribute=attr, slug=opt_slug)
                    .exists()
                )
                if opt_exists:
                    continue
                created_options += 1
                self.stdout.write(f"  + option {code}:{opt_slug}")
                if not dry_run:
                    CatalogAttributeOption.objects.using(db).create(
                        attribute=attr,
                        slug=opt_slug,
                        label=opt_label,
                        active=True,
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_catalog_attributes done: attrs+={created_attrs} "
                f"attrs~={updated_attrs} options+={created_options} dry_run={dry_run}"
            )
        )
