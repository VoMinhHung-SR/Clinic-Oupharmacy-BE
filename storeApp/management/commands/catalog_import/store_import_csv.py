"""
store_import_csv.py
-------------------
Management command: Import scraper output (CSV hoặc JSON) vào storeApp models.

Supports cả 2 format từ product_scraper_tool:
  - .csv: legacy export (flat dotted keys, nested arrays là JSON-string)
  - .json: scraper v1.3.0+ output (array of products, nested dict native)

Schema mapping với scraper JSON v1.3.4:
  - Variants/units lấy từ `pricing.saleUnits[]` (ưu tiên), fallback `pricing.packageOptions`
  - 6 content fields chứa sanitized HTML
  - `ingredients` là comma-list "Name: amount, ..."
  - SKIP `specifications.registrationNumber` (non-import)

Multi-category (ProductCategory M2M):
  - Cùng `mid` + category path khác → merge M2M, không tạo product mới
  - Giữ primary hiện có; set primary chỉ khi product chưa có category
  - `Product.category` FK sync với primary row
"""

from __future__ import annotations

import csv
import json
import logging
import os
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction

from storeApp.constants import STORE_DATABASE_ALIAS

from .store_import_categories import parse_category_array_from_row, resolve_leaf_category
from .store_import_packaging import _build_variant_payloads, _parse_package_options, _parse_price_value
from .store_import_pricing import ensure_unit_pricing, is_positive_price
from .store_import_products import resolve_brand, upsert_product_from_row
from .store_import_row import build_variant_payloads_from_sale_units, flatten_dict, parse_json_field
from .store_import_variants import (
    VariantImportSettings,
    build_variant_common,
    count_simulated_batches,
    create_batches_for_variants,
    upsert_variant_with_units,
)

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = "storeApp/test/data/new"
BATCH_SIZE = 300
DEFAULT_STOCK = 100
DEFAULT_BATCH_COUNT = 1
DEFAULT_BATCH_PACK_MULT_MIN = 10
DEFAULT_BATCH_PACK_MULT_MAX = 40

# Backward-compatible re-exports for tests and audit
from .store_import_row import (  # noqa: E402,F401
    compute_import_price_per_base_unit,
    compute_synthetic_batch_quantity,
)
from .store_import_row import build_variant_payloads_from_sale_units as _build_variant_payloads_from_sale_units
from .store_import_row import parse_json_field as _parse_json_field


class Command(BaseCommand):
    help = (
        "Import scraper output (.csv hoặc .json) vào storeApp models "
        "(Brand, Category, Product, ProductCategory, ProductVariant, ProductVariantUnit, MedicineBatch)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            nargs="?",
            default=DEFAULT_DATA_DIR,
            help=f"Thư mục hoặc file .csv/.json cụ thể (default: {DEFAULT_DATA_DIR})",
        )
        parser.add_argument("--dry-run", action="store_true", help="Validate nhưng không ghi vào DB.")
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Cập nhật Product/Variant nếu đã tồn tại.",
        )
        parser.add_argument("--no-batches", action="store_true", help="Bỏ qua tạo MedicineBatch.")
        parser.add_argument("--limit", type=int, default=None, help="Giới hạn số rows xử lý mỗi file.")
        parser.add_argument(
            "--default-stock",
            type=int,
            default=DEFAULT_STOCK,
            dest="default_stock",
            help=f"in_stock trên variant khi không sync batch (default: {DEFAULT_STOCK}).",
        )
        parser.add_argument(
            "--batch-pack-mult-min",
            type=int,
            default=DEFAULT_BATCH_PACK_MULT_MIN,
            dest="batch_pack_mult_min",
        )
        parser.add_argument(
            "--batch-pack-mult-max",
            type=int,
            default=DEFAULT_BATCH_PACK_MULT_MAX,
            dest="batch_pack_mult_max",
        )
        parser.add_argument(
            "--batch-count",
            type=int,
            default=DEFAULT_BATCH_COUNT,
            dest="batch_count",
        )
        parser.add_argument(
            "--no-smart-random-price",
            action="store_true",
            dest="no_smart_random_price",
            help="Giá thiếu: random phẳng 10k–500k thay vì theo tier đơn vị × quantity_in_base.",
        )

    def handle(self, *args, **options):
        path = options["path"]
        dry_run = bool(options.get("dry_run", False))
        update_existing = bool(options.get("update_existing", False))
        no_batches = bool(options.get("no_batches", False))
        limit = options.get("limit")

        batch_pack_mult_min = max(
            int(options.get("batch_pack_mult_min", DEFAULT_BATCH_PACK_MULT_MIN)), 1
        )
        self.variant_settings = VariantImportSettings(
            default_stock=max(int(options.get("default_stock", DEFAULT_STOCK)), 0),
            batch_pack_mult_min=batch_pack_mult_min,
            batch_pack_mult_max=max(
                int(options.get("batch_pack_mult_max", DEFAULT_BATCH_PACK_MULT_MAX)),
                batch_pack_mult_min,
            ),
            batch_count=max(int(options.get("batch_count", DEFAULT_BATCH_COUNT)), 1),
            using=STORE_DATABASE_ALIAS,
        )
        self.use_smart_random_price = not options.get("no_smart_random_price", False)

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠  DRY-RUN mode — không ghi vào DB."))

        data_files = self._collect_data_files(path)
        if not data_files:
            self.stdout.write(self.style.ERROR(f"Không tìm thấy file .csv/.json nào trong: {path}"))
            return

        self.stdout.write(f"📂 Tìm thấy {len(data_files)} file (csv/json).")

        category_cache: dict = {}
        brand_cache: dict = {}
        total_stats = self._empty_stats()

        for data_file in data_files:
            self.stdout.write(f"\n📄 {os.path.relpath(data_file, os.getcwd())}")
            file_stats = self._import_file(
                data_file=data_file,
                dry_run=dry_run,
                update_existing=update_existing,
                no_batches=no_batches,
                limit=limit,
                category_cache=category_cache,
                brand_cache=brand_cache,
            )
            total_stats["files"] += 1
            for k in file_stats:
                if k in total_stats:
                    total_stats[k] += file_stats.get(k, 0)
            self._print_file_stats(file_stats)

        self._print_summary(total_stats, dry_run, no_batches)

    @staticmethod
    def _empty_stats() -> dict:
        return {
            "files": 0,
            "rows": 0,
            "brands_created": 0,
            "categories_created": 0,
            "products_created": 0,
            "products_updated": 0,
            "product_categories_linked": 0,
            "variants_created": 0,
            "variants_updated": 0,
            "variant_units_created": 0,
            "variant_units_updated": 0,
            "batches_created": 0,
            "errors": 0,
            "units_from_sale_units": 0,
            "units_from_package_options": 0,
        }

    def _collect_data_files(self, path: str):
        if not os.path.isabs(path):
            try:
                from django.conf import settings
                base = str(settings.BASE_DIR)
            except Exception:
                base = os.getcwd()
            path = os.path.join(base, path)

        files = []
        if os.path.isfile(path) and path.endswith((".csv", ".json")):
            return [path]
        if os.path.isdir(path):
            for root, dirs, filenames in os.walk(path):
                dirs.sort()
                for name in sorted(filenames):
                    if name.endswith((".csv", ".json")):
                        files.append(os.path.join(root, name))
        return files

    def _import_file(
        self,
        data_file: str,
        dry_run: bool,
        update_existing: bool,
        no_batches: bool,
        limit: Optional[int],
        category_cache: dict,
        brand_cache: dict,
    ) -> dict:
        stats = self._empty_stats()
        del stats["files"]

        try:
            if data_file.endswith(".json"):
                with open(data_file, encoding="utf-8") as f:
                    items = json.load(f)
                if not isinstance(items, list):
                    items = [items]
                rows = [flatten_dict(it) for it in items if isinstance(it, dict)]
            else:
                with open(data_file, encoding="utf-8-sig") as f:
                    rows = list(csv.DictReader(f))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Không đọc được file: {e}"))
            stats["errors"] += 1
            return stats

        if limit:
            rows = rows[:limit]
        stats["rows"] = len(rows)

        for row_num, row in enumerate(rows, start=1):
            try:
                with transaction.atomic(using=STORE_DATABASE_ALIAS):
                    row_stats = self._process_row(
                        row=row,
                        dry_run=dry_run,
                        update_existing=update_existing,
                        no_batches=no_batches,
                        category_cache=category_cache,
                        brand_cache=brand_cache,
                    )
                for k, v in row_stats.items():
                    stats[k] = stats.get(k, 0) + v
            except Exception as e:
                name = str(row.get("basicInfo.name", "?"))[:60]
                logger.exception("Row %s error (%s)", row_num, name)
                self.stdout.write(self.style.ERROR(f"  ✗ Row {row_num} [{name}]: {e}"))
                stats["errors"] += 1

        return stats

    def _process_row(
        self,
        row: dict,
        dry_run: bool,
        update_existing: bool,
        no_batches: bool,
        category_cache: dict,
        brand_cache: dict,
    ) -> dict:
        stats = self._empty_stats()
        del stats["files"]

        brand_id, brands_created = resolve_brand(
            row, brand_cache, dry_run=dry_run, using=STORE_DATABASE_ALIAS
        )
        stats["brands_created"] = brands_created

        category_array = parse_category_array_from_row(row)
        leaf_category = None
        if category_array:
            leaf_category, cat_new = resolve_leaf_category(
                category_array, category_cache, using=STORE_DATABASE_ALIAS
            )
            stats["categories_created"] = cat_new

        product, product_stats = upsert_product_from_row(
            row,
            brand_id,
            leaf_category,
            update_existing=update_existing,
            dry_run=dry_run,
            using=STORE_DATABASE_ALIAS,
        )
        stats["products_created"] = product_stats["products_created"]
        stats["products_updated"] = product_stats["products_updated"]
        stats["product_categories_linked"] = product_stats["product_categories_linked"]

        if product is None and not dry_run:
            return stats

        variant_payloads, units_source = self._build_variant_payloads_for_row(row)
        stats[units_source] = 1

        for payload in variant_payloads:
            ensure_unit_pricing(
                payload.get("units", []),
                fallback_price=_parse_price_value(
                    str(row.get("pricing.priceDisplay") or row.get("pricing.priceValue") or "")
                ),
                fallback_display=str(row.get("pricing.priceDisplay") or "").strip()[:50],
                use_smart_random=self.use_smart_random_price,
            )

        images = parse_json_field(row.get("media.images", []), default=[])
        image_url = str(row.get("media.image") or "").strip()
        if image_url and image_url not in images:
            images.insert(0, image_url)

        variant_common = build_variant_common(row, images, self.variant_settings)
        created_variants = []

        for payload in variant_payloads:
            if dry_run:
                stats["variants_created"] += 1
                stats["variant_units_created"] += len(payload.get("units", []))
                if not no_batches:
                    stats["batches_created"] += count_simulated_batches(self.variant_settings)
                continue

            variant_instance, created, unit_stats = upsert_variant_with_units(
                product=product,
                payload=payload,
                variant_common=variant_common,
                row=row,
                update_existing=update_existing,
                settings=self.variant_settings,
            )
            if created:
                stats["variants_created"] += 1
            elif update_existing:
                stats["variants_updated"] += 1
            stats["variant_units_created"] += unit_stats.get("created", 0)
            stats["variant_units_updated"] += unit_stats.get("updated", 0)
            created_variants.append(variant_instance)

        if not no_batches and not dry_run and created_variants:
            stats["batches_created"] = create_batches_for_variants(
                created_variants, self.variant_settings
            )

        return stats

    def _build_variant_payloads_for_row(self, row: dict) -> tuple[list, str]:
        default_packing = str(row.get("pricing.packageSize") or "").strip()[:100]
        default_price_display = str(row.get("pricing.priceDisplay") or "").strip()[:50]
        default_price_value = _parse_price_value(
            str(row.get("pricing.priceDisplay") or row.get("pricing.priceValue") or "")
        )

        sale_units = parse_json_field(row.get("pricing.saleUnits"), default=[])
        if sale_units:
            for su in sale_units:
                if isinstance(su, dict) and not is_positive_price(su.get("priceValue")):
                    su["priceValue"] = 0
            return (
                build_variant_payloads_from_sale_units(sale_units, default_packing),
                "units_from_sale_units",
            )

        package_options = _parse_package_options(
            row.get("pricing.packageOptions", ""),
            default_packing=default_packing,
            default_price_display=default_price_display,
            default_price_value=default_price_value,
        )
        return (
            _build_variant_payloads(
                package_options=package_options,
                default_packing=default_packing,
                default_price_display=default_price_display,
                default_price_value=default_price_value,
            ),
            "units_from_package_options",
        )

    def _print_file_stats(self, stats: dict):
        self.stdout.write(
            f"  rows={stats['rows']}  "
            f"product+={stats['products_created']} ~{stats['products_updated']}  "
            f"pcat+={stats.get('product_categories_linked', 0)}  "
            f"variant+={stats['variants_created']} ~{stats['variants_updated']}  "
            f"variantUnit+={stats.get('variant_units_created', 0)} ~{stats.get('variant_units_updated', 0)}  "
            f"brand+={stats['brands_created']}  "
            f"cat+={stats['categories_created']}  "
            f"batch+={stats['batches_created']}  "
            f"err={stats['errors']}"
        )

    def _print_summary(self, total_stats: dict, dry_run: bool, no_batches: bool):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ TỔNG KẾT"))
        self.stdout.write(f"  Files         : {total_stats['files']}")
        self.stdout.write(f"  Rows          : {total_stats['rows']}")
        self.stdout.write(f"  Brands tạo mới: {total_stats['brands_created']}")
        self.stdout.write(f"  Categories    : {total_stats['categories_created']}")
        self.stdout.write(f"  Products tạo  : {total_stats['products_created']}")
        self.stdout.write(f"  Products cập nl: {total_stats['products_updated']}")
        self.stdout.write(f"  ProductCategory links: {total_stats.get('product_categories_linked', 0)}")
        self.stdout.write(f"  Variants tạo  : {total_stats['variants_created']}")
        self.stdout.write(f"  Variants cập nl: {total_stats['variants_updated']}")
        self.stdout.write(f"  VariantUnits tạo : {total_stats['variant_units_created']}")
        self.stdout.write(f"  VariantUnits cập nl: {total_stats['variant_units_updated']}")
        batch_label = "Batches (simulated)" if dry_run and not no_batches else "Batches tạo"
        self.stdout.write(f"  {batch_label:16}: {total_stats['batches_created']}")
        self.stdout.write(
            f"  Units source  : saleUnits={total_stats['units_from_sale_units']}  "
            f"packageOptions={total_stats['units_from_package_options']}"
        )
        self.stdout.write(f"  Lỗi           : {total_stats['errors']}")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠  DRY-RUN complete — không có dữ liệu nào bị lưu."))
