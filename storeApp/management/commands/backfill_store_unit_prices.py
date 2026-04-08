"""
Backfill ProductVariantUnit.price_value when crawl data misses import/base prices.

Strategy priority (practical + safe):
1) Parse from unit.price_display (e.g. "123.000đ")
2) Infer from priced units in same variant (median price per base unit)
3) Infer from priced units in same product (median price per base unit)
4) Infer from priced units in same category (median price per base unit)

Usage:
  python manage.py backfill_store_unit_prices --dry-run
  python manage.py backfill_store_unit_prices
  python manage.py backfill_store_unit_prices --database=store --limit=500
"""

import random
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from django.core.management.base import BaseCommand

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import ProductVariantUnit


def _parse_price_display(raw):
    if not raw:
        return Decimal("0")
    s = str(raw).replace("đ", "").replace(".", "").replace(",", "").strip()
    if not s:
        return Decimal("0")
    try:
        value = Decimal(s)
        return value if value > 0 else Decimal("0")
    except Exception:
        return Decimal("0")


def _to_vnd_display(value):
    # 123456 -> "123.456đ"
    integral = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{integral:,}".replace(",", ".") + "đ"


def _safe_per_base(price_value, quantity_in_base):
    if not price_value or price_value <= 0:
        return None
    qty = int(quantity_in_base or 0)
    if qty <= 0:
        return None
    return Decimal(price_value) / Decimal(qty)


class Command(BaseCommand):
    help = "Backfill zero ProductVariantUnit.price_value using display/sibling/product/category heuristics."

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
            help="Limit number of zero-price units to process (0 = all).",
        )
        parser.add_argument(
            "--unpublish-unresolved",
            action="store_true",
            help="Set is_published=False for units still unresolved after inference.",
        )
        parser.add_argument(
            "--max-consult",
            type=int,
            default=20,
            help="Maximum unresolved units kept at price=0 (CONSULT). Default: 20",
        )
        parser.add_argument(
            "--random-min",
            type=int,
            default=10000,
            help="Min random price (VND) for unresolved units beyond max-consult. Default: 10000",
        )
        parser.add_argument(
            "--random-max",
            type=int,
            default=300000,
            help="Max random price (VND) for unresolved units beyond max-consult. Default: 300000",
        )
        parser.add_argument(
            "--random-seed",
            type=int,
            default=0,
            help="Optional seed for deterministic random pricing (0 = no fixed seed).",
        )

    def handle(self, *args, **options):
        db = options["database"]
        dry_run = options["dry_run"]
        limit = int(options["limit"] or 0)
        unpublish_unresolved = options["unpublish_unresolved"]
        max_consult = max(0, int(options["max_consult"] or 0))
        random_min = int(options["random_min"] or 0)
        random_max = int(options["random_max"] or 0)
        random_seed = int(options["random_seed"] or 0)
        if random_min <= 0 or random_max <= 0 or random_min > random_max:
            raise ValueError("--random-min/--random-max must be positive and random-min <= random-max")
        if random_seed:
            random.seed(random_seed)

        base_qs = ProductVariantUnit.objects.using(db).select_related(
            "variant",
            "variant__product",
            "variant__product__category",
        )
        zero_qs = base_qs.filter(price_value__lte=0)
        if limit > 0:
            zero_qs = zero_qs[:limit]
        zero_units = list(zero_qs)
        if not zero_units:
            self.stdout.write(self.style.SUCCESS("No zero-price units found."))
            return

        # Build pricing pools from all positive priced units
        positive_rows = ProductVariantUnit.objects.using(db).filter(price_value__gt=0).values_list(
            "variant_id",
            "variant__product_id",
            "variant__product__category_id",
            "quantity_in_base",
            "price_value",
        )
        per_variant = {}
        per_product = {}
        per_category = {}
        for variant_id, product_id, category_id, qty, price in positive_rows:
            per_base = _safe_per_base(price, qty)
            if per_base is None:
                continue
            per_variant.setdefault(variant_id, []).append(per_base)
            per_product.setdefault(product_id, []).append(per_base)
            if category_id:
                per_category.setdefault(category_id, []).append(per_base)

        changed = []
        unresolved = []
        unresolved_keep_consult = []
        unresolved_randomized = []
        stats = {
            "parsed_display": 0,
            "same_variant": 0,
            "same_product": 0,
            "same_category": 0,
            "unresolved": 0,
            "kept_consult": 0,
            "randomized": 0,
            "unpublished": 0,
        }

        for unit in zero_units:
            source = None
            new_price = Decimal("0")

            # 1) Parse direct display price
            parsed = _parse_price_display(unit.price_display)
            if parsed > 0:
                new_price = parsed
                source = "parsed_display"
            else:
                # 2) Same variant median per-base
                pool = per_variant.get(unit.variant_id, [])
                if pool:
                    new_price = median(pool) * Decimal(int(unit.quantity_in_base or 1))
                    source = "same_variant"
                else:
                    # 3) Same product median per-base
                    pool = per_product.get(unit.variant.product_id, [])
                    if pool:
                        new_price = median(pool) * Decimal(int(unit.quantity_in_base or 1))
                        source = "same_product"
                    else:
                        # 4) Same category median per-base
                        category_id = unit.variant.product.category_id
                        pool = per_category.get(category_id, []) if category_id else []
                        if pool:
                            new_price = median(pool) * Decimal(int(unit.quantity_in_base or 1))
                            source = "same_category"

            if source and new_price > 0:
                # Normalize to integer VND amount with .00 precision
                normalized = new_price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                unit.price_value = normalized
                if not unit.price_display:
                    unit.price_display = _to_vnd_display(normalized)
                changed.append(unit)
                stats[source] += 1
            else:
                unresolved.append(unit)
                stats["unresolved"] += 1
                if unpublish_unresolved and unit.is_published:
                    unit.is_published = False
                    changed.append(unit)
                    stats["unpublished"] += 1

        # Keep at most N unresolved units as CONSULT(0), random-fill the rest.
        if unresolved:
            unresolved_keep_consult = unresolved[:max_consult]
            unresolved_to_randomize = unresolved[max_consult:]
            for unit in unresolved_to_randomize:
                qty = int(unit.quantity_in_base or 1)
                if qty <= 0:
                    qty = 1
                price = Decimal(random.randint(random_min, random_max))
                unit.price_value = price
                if not unit.price_display:
                    unit.price_display = _to_vnd_display(price)
                changed.append(unit)
                unresolved_randomized.append(unit)
                stats["randomized"] += 1
            stats["kept_consult"] = len(unresolved_keep_consult)

        if not dry_run and changed:
            ProductVariantUnit.objects.using(db).bulk_update(
                changed, ["price_value", "price_display", "is_published"], batch_size=500
            )

        self.stdout.write(
            self.style.NOTICE(
                f"Processed {len(zero_units)} zero-price unit(s) on '{db}'"
                + (" [DRY-RUN]" if dry_run else "")
            )
        )
        self.stdout.write(f"- Backfilled from price_display: {stats['parsed_display']}")
        self.stdout.write(f"- Backfilled from same variant: {stats['same_variant']}")
        self.stdout.write(f"- Backfilled from same product: {stats['same_product']}")
        self.stdout.write(f"- Backfilled from same category: {stats['same_category']}")
        self.stdout.write(f"- Unresolved (still price=0): {stats['unresolved']}")
        self.stdout.write(f"- Kept CONSULT(0): {stats['kept_consult']} (max_consult={max_consult})")
        self.stdout.write(f"- Randomized unresolved: {stats['randomized']} (range={random_min}-{random_max})")
        if unpublish_unresolved:
            self.stdout.write(f"- Unpublished unresolved: {stats['unpublished']}")

        if unresolved_keep_consult:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Sample CONSULT(0) units kept (max 20):"))
            for unit in unresolved_keep_consult[:20]:
                self.stdout.write(
                    f"  - unit_id={unit.id} variant_id={unit.variant_id} "
                    f"product_id={unit.variant.product_id} unit={unit.unit_name} "
                    f"qty_in_base={unit.quantity_in_base}"
                )
        if unresolved_randomized:
            self.stdout.write("")
            self.stdout.write(self.style.NOTICE("Sample randomized units (max 20):"))
            for unit in unresolved_randomized[:20]:
                self.stdout.write(
                    f"  - unit_id={unit.id} variant_id={unit.variant_id} "
                    f"product_id={unit.variant.product_id} unit={unit.unit_name} "
                    f"price_value={unit.price_value}"
                )
