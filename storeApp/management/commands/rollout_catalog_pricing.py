"""
Catalog pricing rollout — audit, cleanup, backfill, verify (P4).

Usage:
  python manage.py rollout_catalog_pricing --audit-only
  python manage.py rollout_catalog_pricing --apply --revert-promo --clear-legacy --backfill-carts --seed-hot-sale
  python manage.py rollout_catalog_pricing --verify [--fail-on-legacy]
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.services.catalog_pricing_audit import (
    audit_catalog_pricing,
    backfill_cart_list_price_snapshots,
    clear_legacy_reverse_compare_at,
    verify_p1_promo_integrity,
)
from storeApp.services.hot_sale_campaign import revert_hot_sale_promotions


class Command(BaseCommand):
    help = "P4 catalog pricing rollout: audit, cleanup legacy compare_at, backfill carts, seed, verify."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=STORE_DATABASE_ALIAS,
            help=f"Django DB alias (default: {STORE_DATABASE_ALIAS})",
        )
        parser.add_argument("--dry-run", action="store_true", help="No writes; show planned counts only.")
        parser.add_argument("--audit-only", action="store_true", help="Print audit report and exit.")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Required with mutation flags (--revert-promo, --clear-legacy, …).",
        )
        parser.add_argument(
            "--revert-promo",
            action="store_true",
            help="Revert active hot-sale ProductUnitPromotion rows (seed_hot_sale --revert-promo).",
        )
        parser.add_argument(
            "--clear-legacy",
            action="store_true",
            help="Null compare_at on P0 reverse-merch units without active promo.",
        )
        parser.add_argument(
            "--backfill-carts",
            action="store_true",
            help="Backfill CartItem.list_price_snapshot from unit compare_at (pre-P2 lines).",
        )
        parser.add_argument(
            "--seed-hot-sale",
            action="store_true",
            help="Run seed_hot_sale_campaign after cleanup.",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Post-rollout checks (schema, promo integrity, audit summary).",
        )
        parser.add_argument(
            "--fail-on-legacy",
            action="store_true",
            help="With --verify: exit non-zero if legacy compare-only units remain.",
        )

    def handle(self, *args, **options):
        db = options["database"]
        dry_run = options["dry_run"]

        if options["audit_only"]:
            self._print_audit(db)
            return

        mutation_flags = (
            options["revert_promo"]
            or options["clear_legacy"]
            or options["backfill_carts"]
            or options["seed_hot_sale"]
        )
        if mutation_flags and not options["apply"] and not dry_run:
            self.stderr.write(
                self.style.ERROR("Mutation steps require --apply (or --dry-run). Use --audit-only to inspect.")
            )
            return

        if mutation_flags or dry_run:
            self._run_mutations(db, dry_run=dry_run, options=options)

        if options["verify"]:
            ok = self._verify(db, fail_on_legacy=options["fail_on_legacy"])
            if not ok:
                self.stderr.write(self.style.ERROR("rollout_catalog_pricing verify: FAILED"))
                return

        if not mutation_flags and not options["verify"] and not options["audit_only"]:
            self.stdout.write("Nothing to do. Try --audit-only, --apply with flags, or --verify.")
            self._print_audit(db)

    def _print_audit(self, db):
        report = audit_catalog_pricing(using=db)
        self.stdout.write(self.style.MIGRATE_HEADING("Catalog pricing audit (P4)"))
        self.stdout.write(f"  units_with_display_discount={report.units_with_display_discount}")
        self.stdout.write(f"  units_with_active_promo={report.units_with_active_promo}")
        self.stdout.write(f"  legacy_compare_only_count={report.legacy_compare_only_count}")
        self.stdout.write(f"  cart_items_missing_list_snapshot={report.cart_items_missing_list_snapshot}")
        self.stdout.write(
            f"  cart_items_with_null_list_but_compare={report.cart_items_with_null_list_but_compare}"
        )
        if report.legacy_rows:
            self.stdout.write("  legacy sample (unit_id price compare_at tier%):")
            for row in report.legacy_rows[:10]:
                self.stdout.write(
                    f"    {row.unit_id} {row.price_value} {row.compare_at_price} "
                    f"-{row.discount_percent}% (tier~{row.tier_match})"
                )

    def _run_mutations(self, db, *, dry_run, options):
        if options["revert_promo"]:
            reverted = revert_hot_sale_promotions(using=db, dry_run=dry_run)
            suffix = " (dry-run)" if dry_run else ""
            self.stdout.write(self.style.SUCCESS(f"revert_hot_sale_promotions: {reverted} unit(s){suffix}"))

        if options["clear_legacy"]:
            cleared = clear_legacy_reverse_compare_at(using=db, dry_run=dry_run)
            suffix = " (dry-run)" if dry_run else ""
            self.stdout.write(self.style.SUCCESS(f"clear_legacy_reverse_compare_at: {cleared} unit(s){suffix}"))

        if options["backfill_carts"]:
            updated = backfill_cart_list_price_snapshots(using=db, dry_run=dry_run)
            suffix = " (dry-run)" if dry_run else ""
            self.stdout.write(self.style.SUCCESS(f"backfill_cart_list_price_snapshots: {updated} line(s){suffix}"))

        if options["seed_hot_sale"] and not dry_run:
            call_command("seed_hot_sale_campaign", database=db)
            self.stdout.write(self.style.SUCCESS("seed_hot_sale_campaign: done"))
        elif options["seed_hot_sale"] and dry_run:
            call_command("seed_hot_sale_campaign", database=db, dry_run=True)

    def _verify(self, db, *, fail_on_legacy: bool) -> bool:
        ok = True
        self.stdout.write(self.style.MIGRATE_HEADING("Catalog pricing verify (P4)"))

        if not self._column_exists(db, "store_cart", "catalog_direct_savings_total"):
            self.stderr.write(self.style.ERROR("Missing store_cart.catalog_direct_savings_total — run migrate storeApp"))
            ok = False
        else:
            self.stdout.write("  schema: cart P2 columns OK")

        if not self._column_exists(db, "store_cart_item", "list_price_snapshot"):
            self.stderr.write(self.style.ERROR("Missing store_cart_item.list_price_snapshot — run migrate storeApp"))
            ok = False
        else:
            self.stdout.write("  schema: cart_item list_price_snapshot OK")

        issues = verify_p1_promo_integrity(using=db)
        if issues:
            ok = False
            self.stderr.write(self.style.WARNING(f"  promo integrity: {len(issues)} issue(s)"))
            for msg in issues[:5]:
                self.stderr.write(f"    {msg}")
        else:
            self.stdout.write("  promo integrity: OK")

        report = audit_catalog_pricing(using=db, legacy_sample=5)
        self.stdout.write(f"  legacy_compare_only_count={report.legacy_compare_only_count}")
        if fail_on_legacy and report.legacy_compare_only_count > 0:
            ok = False

        if ok:
            self.stdout.write(self.style.SUCCESS("rollout_catalog_pricing verify: OK"))
        return ok

    def _column_exists(self, db, table: str, column: str) -> bool:
        conn = connection
        if db != "default":
            from django.db import connections

            conn = connections[db]
        with conn.cursor() as cursor:
            description = conn.introspection.get_table_description(cursor, table)
        return any(col.name == column for col in description)
