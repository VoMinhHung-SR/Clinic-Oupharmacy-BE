#!/usr/bin/env python3
"""
Quick stats checker for store product data.

Usage:
  python scripts/check_store_product_stats.py
  python scripts/check_store_product_stats.py --database store
"""

import argparse
import os
import sys


def bootstrap_django() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "OUPharmacyManagementApp.settings")

    import django  # pylint: disable=import-outside-toplevel

    django.setup()


def format_int(value: int) -> str:
    return f"{value:,}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check product/variant/unit/batch stats in store app."
    )
    parser.add_argument(
        "--database",
        default="store",
        help="Django DB alias to query (default: store).",
    )
    args = parser.parse_args()

    bootstrap_django()

    from django.db.models import Count, Q  # pylint: disable=import-outside-toplevel
    from django.utils import timezone  # pylint: disable=import-outside-toplevel
    from storeApp.models import (  # pylint: disable=import-outside-toplevel
        MedicineBatch,
        Product,
        ProductVariant,
        ProductVariantUnit,
    )

    db = args.database

    total_products = Product.objects.using(db).count()
    total_variants = ProductVariant.objects.using(db).count()
    total_units = ProductVariantUnit.objects.using(db).count()
    total_batches = MedicineBatch.objects.using(db).count()
    total_units_price_zero = ProductVariantUnit.objects.using(db).filter(price_value=0).count()
    total_expired_batches = MedicineBatch.objects.using(db).filter(expiry_date__lt=timezone.localdate()).count()
    total_variants_gt_2_units = (
        ProductVariant.objects.using(db)
        .annotate(unit_count=Count("units"))
        .filter(unit_count__gt=2)
        .count()
    )
    total_outdated_products = (
        Product.objects.using(db)
        .filter(variants__batches__expiry_date__lt=timezone.localdate())
        .distinct()
        .count()
    )

    # "Options" được hiểu là số phần tử trong packing_meta.packageOptions của từng variant.
    total_options = 0
    for variant in ProductVariant.objects.using(db).only("packing_meta").iterator():
        packing_meta = variant.packing_meta or {}
        package_options = packing_meta.get("packageOptions", [])
        if isinstance(package_options, list):
            total_options += len(package_options)

    print("=== STORE PRODUCT STATS ===")
    print(f"Database alias: {db}")
    print(f"Total products : {format_int(total_products)}")
    print(f"Total variants : {format_int(total_variants)}")
    print(f"Total options  : {format_int(total_options)}")
    print(f"Total units    : {format_int(total_units)}")
    print(f"Units price=0  : {format_int(total_units_price_zero)}")
    print(f"Total batches  : {format_int(total_batches)}")
    print(f"Expired batches: {format_int(total_expired_batches)}")
    print(f"Variants >2 unit: {format_int(total_variants_gt_2_units)}")
    print(f"Outdated products: {format_int(total_outdated_products)}")

    print("")
    print("=== DATA QUALITY / IMPORT CONDITIONS ===")
    print(f"Condition outdated products > 2,000: {'YES' if total_outdated_products > 2000 else 'NO'}")

    # Kiểm tra trùng batch_number (theo logic chuẩn thì không nên có vì có unique constraint).
    duplicated_batch_numbers = (
        MedicineBatch.objects.using(db)
        .values("batch_number")
        .annotate(row_count=Count("id"), variant_count=Count("product_variant_id", distinct=True))
        .filter(row_count__gt=1)
        .order_by("-row_count", "batch_number")
    )
    duplicate_count = duplicated_batch_numbers.count()
    print(f"Duplicated batch_number rows: {format_int(duplicate_count)}")
    if duplicate_count > 0:
        print("Sample duplicated batches (max 20):")
        for row in duplicated_batch_numbers[:20]:
            print(
                f"- batch={row['batch_number']} | rows={row['row_count']} | "
                f"variants={row['variant_count']}"
            )

    # Nếu variant chỉ có 1 lô và lô đó đã hết hạn -> cần nhập lô mới.
    variants_need_new_batch = (
        ProductVariant.objects.using(db)
        .annotate(
            batch_count=Count("batches", distinct=True),
            expired_batch_count=Count(
                "batches",
                filter=Q(batches__expiry_date__lt=timezone.localdate()),
                distinct=True,
            ),
        )
        .filter(batch_count=1, expired_batch_count=1)
        .select_related("product")
        .order_by("id")
    )
    need_new_batch_count = variants_need_new_batch.count()
    print(f"Variants with only 1 expired batch (need import new batch): {format_int(need_new_batch_count)}")
    if need_new_batch_count > 0:
        print("Sample variants need new batch (max 30):")
        for variant in variants_need_new_batch[:30]:
            print(f"- variant_id={variant.id} | product={variant.product.name} | packing={variant.packing}")

    # Product không có bất kỳ variant nào.
    products_without_variants = (
        Product.objects.using(db)
        .annotate(variant_count=Count("variants"))
        .filter(variant_count=0)
        .order_by("id")
    )
    missing_variant_count = products_without_variants.count()
    print(f"Products without variants: {format_int(missing_variant_count)}")
    if missing_variant_count > 0:
        print("List products without variants:")
        for product in products_without_variants:
            print(f"- product_id={product.id} | name={product.name}")

    products_with_multiple_variants = (
        Product.objects.using(db)
        .annotate(variant_count=Count("variants"))
        .filter(variant_count__gt=1)
        .order_by("-variant_count", "id")
    )
    multiple_variant_count = products_with_multiple_variants.count()
    print(f"Products with >1 variant: {format_int(multiple_variant_count)}")
    if multiple_variant_count > 0:
        print("List products with >1 variant:")
        for product in products_with_multiple_variants:
            print(
                f"- product_id={product.id} | variants={product.variant_count} | "
                f"name={product.name}"
            )


if __name__ == "__main__":
    main()
