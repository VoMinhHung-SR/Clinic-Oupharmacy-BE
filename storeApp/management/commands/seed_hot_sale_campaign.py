"""
Seed hot-sale campaign — real catalog tier promos (P1 / D-PRC Option 1).

Lowers price_value and sets compare_at to list reference. Revert restores snapshots.

Usage:
  python manage.py store_import_vouchers
  python manage.py seed_hot_sale_campaign
  python manage.py seed_hot_sale_campaign --dry-run
  python manage.py seed_hot_sale_campaign --revert-promo
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.services.hot_sale_campaign import (
    HOT_SALE_CAMPAIGN_SLUG,
    HOT_SALE_FETCH_SIZE,
    HOT_SALE_PAGE_SIZE,
    fetch_popular_variants_for_hot_sale,
    plan_hot_sale_rows,
    revert_hot_sale_promotions,
    upsert_hot_sale_campaign,
)


class Command(BaseCommand):
    help = (
        "Upsert san-pham-ban-chay: popular products with real tier promos "
        "(lowers price_value; compare_at = list). Revert: --revert-promo."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=STORE_DATABASE_ALIAS,
            help=f"Django DB alias (default: {STORE_DATABASE_ALIAS})",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--page-size",
            type=int,
            default=HOT_SALE_PAGE_SIZE,
            help=f"Max products in campaign (default: {HOT_SALE_PAGE_SIZE})",
        )
        parser.add_argument(
            "--fetch-size",
            type=int,
            default=HOT_SALE_FETCH_SIZE,
            help=f"Popular pool fetch size before CONSULT filter (default: {HOT_SALE_FETCH_SIZE})",
        )
        parser.add_argument(
            "--priority",
            type=int,
            default=150,
            help="Campaign priority (default 150).",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Active window length from now (default 90 days).",
        )
        parser.add_argument(
            "--revert-promo",
            action="store_true",
            help=f"Restore unit prices from ProductUnitPromotion for {HOT_SALE_CAMPAIGN_SLUG}.",
        )
        parser.add_argument(
            "--revert-compare",
            action="store_true",
            help="Alias for --revert-promo (restores price_value + compare_at).",
        )

    def handle(self, *args, **options):
        db = options["database"]
        dry_run = options["dry_run"]

        if options["revert_promo"] or options["revert_compare"]:
            reverted = revert_hot_sale_promotions(using=db, dry_run=dry_run)
            suffix = " (dry-run)" if dry_run else ""
            self.stdout.write(
                self.style.SUCCESS(f"revert_hot_sale_promotions: restored {reverted} unit(s){suffix}")
            )
            return

        now = timezone.now()
        start = now - timedelta(days=1)
        end = now + timedelta(days=options["days"])

        variants = fetch_popular_variants_for_hot_sale(db, fetch_size=options["fetch_size"])
        plans = plan_hot_sale_rows(variants, page_size=options["page_size"])

        if not plans:
            self.stdout.write(
                self.style.WARNING(
                    "No priced popular products with product.mid — import/sync catalog first."
                )
            )
            return

        for plan in plans:
            promo = plan.promo
            self.stdout.write(
                f"+ {plan.product_mid} tier={plan.tier_percent}% "
                f"list={promo.list_price} sale={promo.sale_price} "
                f"effective={promo.discount_percent}%"
            )

        campaign = upsert_hot_sale_campaign(
            plans,
            using=db,
            dry_run=dry_run,
            start_at=start,
            end_at=end,
            priority=options["priority"],
        )

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"dry-run: would upsert {len(plans)} promoted products"))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_hot_sale_campaign done: {HOT_SALE_CAMPAIGN_SLUG} id={campaign.id} "
                f"products={len(plans)} landing=/khuyen-mai/{HOT_SALE_CAMPAIGN_SLUG}"
            )
        )
