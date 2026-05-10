"""
store_import_csv.py
-------------------
Management command: Import scraper output (CSV hoặc JSON) vào storeApp models.

Supports cả 2 format từ product_scraper_tool:
  - .csv: legacy export (flat dotted keys, nested arrays là JSON-string)
  - .json: scraper v1.3.0+ output (array of products, nested dict native)

Schema mapping với scraper JSON v1.3.4:
  - Variants/units lấy từ `pricing.saleUnits[]` (ưu tiên), fallback `pricing.packageOptions`
  - 6 content fields chứa sanitized HTML (description/usage/dosage/adverseEffect/careful/preservation)
  - `ingredients` là comma-list "Name: amount, ..."
  - SKIP `specifications.registrationNumber` (scraper output đang concatenated garbage)
"""

import csv
import json
import logging
import os
import random
from datetime import date, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from .store_import_packaging import (
    _build_variant_payloads,
    _normalize_unit_name,
    _parse_package_options,
    _parse_price_value,
    normalize_single_default_unit_per_variant,
    reconcile_single_default_variant_units_in_db,
)
from storeApp.models import (
    Brand,
    Category,
    MedicineBatch,
    Product,
    ProductVariant,
    ProductVariantUnit,
    ProductVariantStats,
)
from storeApp.services.stock import sync_in_stock_cache

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = "storeApp/test/data/new"
BATCH_SIZE = 300  # bulk_create chunk size

# ============================================================
# Helper utilities
# ============================================================

def _parse_json_field(raw, default=None):
    if default is None:
        default = []
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return default
    try:
        result = json.loads(raw)
        return result if result is not None else default
    except (json.JSONDecodeError, TypeError):
        return default


def _flatten_dict(item: dict, prefix: str = "") -> dict:
    """Nested dict → flat dotted dict; lists/scalars stop recursion."""
    out: dict = {}
    for k, v in item.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_dict(v, key))
        else:
            out[key] = v
    return out


def _build_variant_payloads_from_sale_units(
    sale_units: list,
    default_packing: str,
) -> list:
    """Direct payload từ scraper saleUnits[] (giữ unitOrder + isDefault gốc)."""
    if not sale_units:
        return []

    units = []
    for su in sale_units:
        if not isinstance(su, dict):
            continue
        unit_name = (su.get("unitName") or "").strip()
        if not unit_name:
            continue
        units.append({
            "unit_name": unit_name[:50],
            "unit_order": _to_int(su.get("unitOrder"), 0),
            "quantity_in_base": max(_to_int(su.get("quantityInBase"), 1), 1),
            "price_value": float(su.get("priceValue") or 0),
            "price_display": (str(su.get("priceDisplay") or "").strip())[:50] or None,
            "is_default": bool(su.get("isDefault")),
        })

    if not units:
        return []

    units.sort(key=lambda u: (u["unit_order"], 0 if u["is_default"] else 1))
    normalize_single_default_unit_per_variant(units)
    base_unit = units[0]["unit_name"]
    packing = (default_packing or "").strip()[:100] or "Default"
    return [{"packing": packing, "base_unit": base_unit, "units": units}]


def _to_int(value, default=0) -> int:
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


def _to_bool(value, default=False) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on") if value else default


def _normalize_brand(name: str) -> Optional[str]:
    if not name:
        return None
    normalized = " ".join(name.strip().split())
    return normalized or None


COUNTRY_MAP = {
    "úc": "Úc", "australia": "Úc",
    "pháp": "Pháp", "france": "Pháp",
    "đức": "Đức", "germany": "Đức",
    "mỹ": "Mỹ", "usa": "Mỹ", "hoa kỳ": "Mỹ",
    "anh": "Anh", "uk": "Anh", "united kingdom": "Anh", "england": "Anh",
    "nhật": "Nhật Bản", "japan": "Nhật Bản",
    "hàn quốc": "Hàn Quốc", "korea": "Hàn Quốc", "south korea": "Hàn Quốc",
    "trung quốc": "Trung Quốc", "china": "Trung Quốc",
    "ấn độ": "Ấn Độ", "india": "Ấn Độ",
    "thái lan": "Thái Lan", "thailand": "Thái Lan",
    "pakistan": "Pakistan",
    "việt nam": "Việt Nam", "vietnam": "Việt Nam",
    "hungary": "Hungary",
    "thuỵ điển": "Thụy Điển", "sweden": "Thụy Điển",
    "ý": "Ý", "italy": "Ý",
    "tây ban nha": "Tây Ban Nha", "spain": "Tây Ban Nha",
}


def _extract_country(text: str) -> Optional[str]:
    if not text:
        return None
    lower = text.lower()
    for key, country in COUNTRY_MAP.items():
        if key in lower:
            return country
    return None


def _add_months(d: date, months: int) -> date:
    return d + relativedelta(months=months)


def _random_import_date(today: date) -> date:
    """Random ngày nhập kho trong 6-12 tháng qua (trước today)."""
    start = _add_months(today, -12)
    end = _add_months(today, -6)
    delta = max((end - start).days, 1)
    return start + timedelta(days=random.randint(0, delta))


_RANDOM_PRICE_RANGE = (10_000, 500_000)
_RANDOM_SHELF_LIFE_MONTHS = (12, 18, 24, 36)


def _random_price_value() -> float:
    return float(random.randint(*_RANDOM_PRICE_RANGE))


def _format_price_display(value: float, unit_name: str = "") -> str:
    s = f"{int(value):,}".replace(",", ".") + "đ"
    return f"{s} / {unit_name}" if unit_name else s


def _random_shelf_life() -> str:
    return f"{random.choice(_RANDOM_SHELF_LIFE_MONTHS)} tháng"


def _ensure_unit_pricing(units: list) -> None:
    for u in units:
        if not u.get("price_value"):
            u["price_value"] = _random_price_value()
            if not u.get("price_display"):
                u["price_display"] = _format_price_display(u["price_value"], u.get("unit_name", ""))


# ============================================================
# StoreApp Category helper (mirror of Category.get_or_create_from_array
# but using StoreCategory via 'store' DB alias)
# ============================================================

def _get_or_create_store_category(category_array: list, cache: dict) -> Optional[Category]:
    """
    category_array: [{'name': '...', 'slug': '...'}, ...]
    Returns leaf Category (storeApp) or None.
    """
    if not category_array:
        return None

    parent = None
    for item in category_array:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip()
        slug = item.get("slug", "").strip()
        if not name or not slug:
            continue

        cache_key = (parent.id if parent else None, slug)
        if cache_key in cache:
            parent = cache[cache_key]
        else:
            cat, _ = Category.objects.using("store").get_or_create(
                slug=slug,
                parent=parent,
                defaults={"name": name},
            )
            cache[cache_key] = cat
            parent = cat

    return parent  # leaf


# ============================================================
# Management Command
# ============================================================

class Command(BaseCommand):
    help = (
        "Import scraper output (.csv hoặc .json) vào storeApp models "
        "(Brand, Category, Product, ProductVariant, ProductVariantUnit, MedicineBatch, ProductVariantStats)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            nargs="?",
            default=DEFAULT_DATA_DIR,
            help=f"Thư mục hoặc file .csv/.json cụ thể (default: {DEFAULT_DATA_DIR})",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate nhưng không ghi vào DB.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Cập nhật Product/Variant nếu đã tồn tại.",
        )
        parser.add_argument(
            "--no-batches",
            action="store_true",
            help="Bỏ qua tạo MedicineBatch.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Giới hạn số rows xử lý mỗi file (dùng để test).",
        )

    # ----------------------------------------------------------
    # Entry point
    # ----------------------------------------------------------
    def handle(self, *args, **options):
        path = options["path"]
        dry_run = options["dry_run"]
        update_existing = options["update_existing"]
        no_batches = options["no_batches"]
        limit = options.get("limit")

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠  DRY-RUN mode — không ghi vào DB."))

        data_files = self._collect_data_files(path)
        if not data_files:
            self.stdout.write(self.style.ERROR(f"Không tìm thấy file .csv/.json nào trong: {path}"))
            return

        self.stdout.write(f"📂 Tìm thấy {len(data_files)} file (csv/json).")

        # Shared caches across files
        category_cache: dict = {}
        brand_cache: dict = {}  # brand_name → Brand.id

        total_stats = {
            "files": 0,
            "rows": 0,
            "brands_created": 0,
            "categories_created": 0,
            "products_created": 0,
            "products_updated": 0,
            "variants_created": 0,
            "variants_updated": 0,
            "variant_units_created": 0,
            "variant_units_updated": 0,
            "batches_created": 0,
            "errors": 0,
        }

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
            for k in ("rows", "brands_created", "categories_created",
                      "products_created", "products_updated",
                      "variants_created", "variants_updated",
                      "variant_units_created", "variant_units_updated",
                      "batches_created", "errors"):
                total_stats[k] += file_stats.get(k, 0)

            self._print_file_stats(file_stats)

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ TỔNG KẾT"))
        self.stdout.write(f"  Files         : {total_stats['files']}")
        self.stdout.write(f"  Rows          : {total_stats['rows']}")
        self.stdout.write(f"  Brands tạo mới: {total_stats['brands_created']}")
        self.stdout.write(f"  Categories    : {total_stats['categories_created']}")
        self.stdout.write(f"  Products tạo  : {total_stats['products_created']}")
        self.stdout.write(f"  Products cập nl: {total_stats['products_updated']}")
        self.stdout.write(f"  Variants tạo  : {total_stats['variants_created']}")
        self.stdout.write(f"  Variants cập nl: {total_stats['variants_updated']}")
        self.stdout.write(f"  VariantUnits tạo : {total_stats['variant_units_created']}")
        self.stdout.write(f"  VariantUnits cập nl: {total_stats['variant_units_updated']}")
        self.stdout.write(f"  Batches tạo   : {total_stats['batches_created']}")
        self.stdout.write(f"  Lỗi           : {total_stats['errors']}")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠  DRY-RUN complete — không có dữ liệu nào bị lưu."))

    # ----------------------------------------------------------
    # Collect data files (.csv + .json)
    # ----------------------------------------------------------
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

    # ----------------------------------------------------------
    # Import 1 file (csv hoặc json)
    # ----------------------------------------------------------
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
        stats = {
            "rows": 0,
            "brands_created": 0,
            "categories_created": 0,
            "products_created": 0,
            "products_updated": 0,
            "variants_created": 0,
            "variants_updated": 0,
            "variant_units_created": 0,
            "variant_units_updated": 0,
            "batches_created": 0,
            "errors": 0,
        }

        try:
            if data_file.endswith(".json"):
                with open(data_file, encoding="utf-8") as f:
                    items = json.load(f)
                if not isinstance(items, list):
                    items = [items]
                rows = [_flatten_dict(it) for it in items if isinstance(it, dict)]
            else:
                with open(data_file, encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Không đọc được file: {e}"))
            stats["errors"] += 1
            return stats

        if limit:
            rows = rows[:limit]

        stats["rows"] = len(rows)

        for row_num, row in enumerate(rows, start=1):
            try:
                # Use sub-transaction to allow continuing on row error
                # Note: atomic(using='store') because we are writing to the store DB
                with transaction.atomic(using="store"):
                    row_stats = self._process_row(
                        row=row,
                        dry_run=dry_run,
                        update_existing=update_existing,
                        no_batches=no_batches,
                        category_cache=category_cache,
                        brand_cache=brand_cache,
                    )
                # Aggregate stats (including dry-run stats)
                for k, v in row_stats.items():
                    stats[k] = stats.get(k, 0) + v
            except Exception as e:
                name = str(row.get("basicInfo.name", "?"))[:60]
                logger.exception(f"Row {row_num} error ({name})")
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Row {row_num} [{name}]: {e}")
                )
                stats["errors"] += 1

        return stats

    # ----------------------------------------------------------
    # Process 1 CSV row
    # ----------------------------------------------------------
    def _process_row(
        self,
        row: dict,
        dry_run: bool,
        update_existing: bool,
        no_batches: bool,
        category_cache: dict,
        brand_cache: dict,
    ) -> dict:
        stats = {
            "brands_created": 0,
            "categories_created": 0,
            "products_created": 0,
            "products_updated": 0,
            "variants_created": 0,
            "variants_updated": 0,
            "variant_units_created": 0,
            "variant_units_updated": 0,
            "batches_created": 0,
        }

        # ── 1. Brand ──────────────────────────────────────────
        brand_id = self._resolve_brand(row, brand_cache, dry_run, stats)

        # ── 2. Category ───────────────────────────────────────
        category_array = _parse_json_field(row.get("category.category", "[]"), default=[])
        leaf_category = None
        if category_array:
            prev_count = len(category_cache)
            leaf_category = _get_or_create_store_category(category_array, category_cache)
            # Count new categories even in dry-run
            stats["categories_created"] += max(0, len(category_cache) - prev_count)

        # ── 3. Product ────────────────────────────────────────
        product = self._resolve_product(row, brand_id, leaf_category, update_existing, dry_run, stats)
        if product is None and not dry_run:
            return stats  # name missing

        # ── 4. ProductVariants ────────────────────────────────
        default_packing = str(row.get("pricing.packageSize") or "").strip()[:100]
        default_price_display = str(row.get("pricing.priceDisplay") or "").strip()[:50]
        default_price_value = _parse_price_value(
            str(row.get("pricing.priceDisplay") or row.get("pricing.priceValue") or "")
        )

        sale_units = row.get("pricing.saleUnits")
        if isinstance(sale_units, list) and sale_units:
            variant_payloads = _build_variant_payloads_from_sale_units(
                sale_units=sale_units,
                default_packing=default_packing,
            )
        else:
            package_options = _parse_package_options(
                row.get("pricing.packageOptions", ""),
                default_packing=default_packing,
                default_price_display=default_price_display,
                default_price_value=default_price_value,
            )
            variant_payloads = _build_variant_payloads(
                package_options=package_options,
                default_packing=default_packing,
                default_price_display=default_price_display,
                default_price_value=default_price_value,
            )

        for payload in variant_payloads:
            _ensure_unit_pricing(payload.get("units", []))

        images = _parse_json_field(row.get("media.images", []), default=[])
        image_url = str(row.get("media.image") or "").strip()
        if image_url and image_url not in images:
            images.insert(0, image_url)

        shelf_life = str(row.get("specifications.shelfLife") or "").strip()[:100] or _random_shelf_life()

        variant_common = {
            "in_stock": random.randint(50, 300),
            "image": None,
            "images": images,
            "base_unit": "unit",
            "packing_meta": {
                "origin": str(row.get("specifications.origin") or "").strip()[:200],
                "manufacturer": str(row.get("specifications.manufacturer") or "").strip(),
                "shelf_life": shelf_life,
            },
            "product_ranking": _to_int(row.get("metadata.productRanking"), 0),
            "sku": str(row.get("basicInfo.sku") or "").strip()[:100] or None,
            "is_published": _to_bool(row.get("metadata.isPublish", "true"), True),
            "is_hot": _to_bool(row.get("metadata.isHot", "false"), False),
        }

        created_variants: list[ProductVariant] = []

        for payload in variant_payloads:
            if dry_run:
                stats["variants_created"] += 1
                stats["variant_units_created"] += len(payload.get("units", []))
                continue

            variant_instance, created, unit_stats = self._upsert_variant_with_units(
                product=product,
                payload=payload,
                variant_common=variant_common,
                row=row,
                update_existing=update_existing,
            )
            if created:
                stats["variants_created"] += 1
            elif update_existing:
                stats["variants_updated"] += 1
            stats["variant_units_created"] += unit_stats.get("created", 0)
            stats["variant_units_updated"] += unit_stats.get("updated", 0)
            created_variants.append(variant_instance)

        # ── 5. MedicineBatch ──────────────────────────────────
        if not no_batches and not dry_run and created_variants:
            batch_count = self._create_batches(created_variants)
            stats["batches_created"] += batch_count

        return stats

    def _upsert_variant_with_units(
        self,
        product: Product,
        payload: dict,
        variant_common: dict,
        row: dict,
        update_existing: bool,
    ) -> tuple[ProductVariant, bool, dict]:
        packing = payload["packing"]
        units = payload["units"]
        base_unit = payload["base_unit"]

        variant_fields = {
            **variant_common,
            "packing": packing,
            "base_unit": base_unit[:50],
            "packing_meta": {
                **variant_common.get("packing_meta", {}),
                "units": [u["unit_name"] for u in units],
            },
        }

        existing_variant = (
            ProductVariant.objects.using("store")
            .filter(product=product, packing=packing)
            .first()
        )

        if existing_variant:
            if update_existing:
                for field, val in variant_fields.items():
                    setattr(existing_variant, field, val)
                existing_variant.save(using="store")
            variant_instance = existing_variant
            created = False
        else:
            variant_instance = ProductVariant.objects.using("store").create(
                product=product,
                **variant_fields,
            )
            created = True

        ProductVariantStats.objects.using("store").get_or_create(
            variant=variant_instance,
            defaults={
                "sold_total": 0,
                "sold_30d": 0,
                "sold_7d": 0,
                "view_count": 0,
                "wishlist_count": 0,
            },
        )
        unit_stats = self._upsert_variant_units(
            variant=variant_instance,
            units=units,
            is_published=_to_bool(row.get("metadata.isPublish", "true"), True),
            update_existing=update_existing,
        )
        return variant_instance, created, unit_stats

    def _upsert_variant_units(self, variant: ProductVariant, units: list, is_published: bool, update_existing: bool) -> dict:
        # Một variant: đúng một is_default=True trong payload (CSV/packageOptions có thể thiếu hoặc trùng).
        normalize_single_default_unit_per_variant(units)
        stats = {"created": 0, "updated": 0}

        existing_units = {
            _normalize_unit_name(unit.unit_name): unit
            for unit in ProductVariantUnit.objects.using("store").filter(variant=variant)
        }

        for unit in units:
            unit_key = _normalize_unit_name(unit["unit_name"])
            unit_defaults = {
                "quantity_in_base": unit.get("quantity_in_base", 1),
                "unit_name": unit["unit_name"][:50],
                "unit_order": unit.get("unit_order", 0),
                "price_value": unit.get("price_value") or 0,
                "price_display": unit.get("price_display") or None,
                "compare_at_price": None,
                "is_default": bool(unit.get("is_default")),
                "is_published": is_published,
            }
            existing_unit = existing_units.get(unit_key)
            if existing_unit:
                if update_existing:
                    for field, val in unit_defaults.items():
                        setattr(existing_unit, field, val)
                    existing_unit.save(using="store")
                    stats["updated"] += 1
            else:
                ProductVariantUnit.objects.using("store").create(
                    variant=variant,
                    **unit_defaults,
                )
                stats["created"] += 1

        # Có thể còn unit cũ trên DB không nằm trong payload → đồng bộ lại đúng 1 default / variant.
        reconcile_single_default_variant_units_in_db(variant, using="store")
        return stats

    # ----------------------------------------------------------
    # Brand resolution
    # ----------------------------------------------------------
    def _resolve_brand(self, row: dict, brand_cache: dict, dry_run: bool, stats: dict) -> Optional[int]:
        raw_name = str(row.get("basicInfo.brand") or "").strip()
        brand_name = _normalize_brand(raw_name)
        if not brand_name:
            return None

        if brand_name in brand_cache:
            brand_id = brand_cache[brand_name]
            # Update country nếu có thông tin mới
            if not dry_run:
                country = self._extract_country_from_row(row)
                if country:
                    Brand.objects.using("store").filter(id=brand_id, country__isnull=True).update(country=country)
                    Brand.objects.using("store").filter(id=brand_id).exclude(country=country).update(country=country)
            return brand_id

        if dry_run:
            brand_cache[brand_name] = -1  # sentinel
            stats["brands_created"] += 1
            return None

        country = self._extract_country_from_row(row)
        brand, created = Brand.objects.using("store").get_or_create(
            name=brand_name,
            defaults={"country": country, "active": True},
        )
        if created:
            stats["brands_created"] += 1
        elif country and brand.country != country:
            brand.country = country
            brand.save(update_fields=["country"])

        brand_cache[brand_name] = brand.id
        return brand.id

    def _extract_country_from_row(self, row: dict) -> Optional[str]:
        for field in ("basicInfo.country", "brand.country", "specifications.country"):
            val = str(row.get(field) or "").strip()
            if val:
                return _extract_country(val) or val
        for field in ("specifications.origin", "specifications.manufacturer"):
            val = str(row.get(field) or "").strip()
            country = _extract_country(val)
            if country:
                return country
        return None

    # ----------------------------------------------------------
    # Product resolution
    # ----------------------------------------------------------
    def _resolve_product(
        self,
        row: dict,
        brand_id: Optional[int],
        leaf_category: Optional[Category],
        update_existing: bool,
        dry_run: bool,
        stats: dict,
    ) -> Optional[Product]:
        name = str(row.get("basicInfo.name") or "").strip()
        if not name:
            return None

        sku_raw = row.get("basicInfo.sku")
        mid = str(sku_raw).strip() if sku_raw not in (None, "") else None
        slug = str(row.get("basicInfo.slug") or "").strip() or None

        def _txt(key):
            return str(row.get(key) or "").strip() or None

        product_defaults = {
            "name": name,
            "mid": mid,
            "slug": slug,
            "web_name": _txt("basicInfo.webName"),
            "description": _txt("content.description"),
            "ingredients": _txt("content.ingredients"),
            "usage": _txt("content.usage"),
            "dosage": _txt("content.dosage"),
            "adverse_effect": _txt("content.adverseEffect"),
            "careful": _txt("content.careful"),
            "preservation": _txt("content.preservation"),
            "brand_id": brand_id,
            "category": leaf_category,
        }

        if dry_run:
            stats["products_created"] += 1
            return None

        # Lookup: mid (sku) → slug → name
        product = None
        if mid:
            product = Product.objects.using("store").filter(mid=mid).first()
        if not product and slug:
            product = Product.objects.using("store").filter(slug=slug).first()
        if not product:
            product = Product.objects.using("store").filter(name=name).first()

        if product:
            if update_existing:
                update_fields = []
                for field, val in product_defaults.items():
                    if getattr(product, field if not field.endswith("_id") else field, None) != val:
                        setattr(product, field, val)
                        update_fields.append(field)
                if update_fields:
                    product.save(using="store", update_fields=update_fields)
                    stats["products_updated"] += 1
        else:
            product = Product.objects.using("store").create(**product_defaults)
            stats["products_created"] += 1

        return product

    # ----------------------------------------------------------
    # MedicineBatch creation
    # ----------------------------------------------------------
    def _create_batches(self, variants: list) -> int:
        today = timezone.now().date()
        created = 0
        used_numbers: set = set(
            MedicineBatch.objects.using("store").values_list("batch_number", flat=True)
        )

        for variant in variants:
            # Xóa batch cũ của variant này (tránh conflict)
            MedicineBatch.objects.using("store").filter(product_variant=variant).delete()

            # Tạo 1-2 batch mới
            num_batches = random.randint(1, 2)
            for _ in range(num_batches):
                import_date = _random_import_date(today)
                expiry_months = random.choice([6, 12, 18, 24, 36])
                expiry_date = _add_months(import_date, expiry_months)
                quantity = random.randint(50, 500)

                # Unique batch_number
                for _ in range(50):
                    suffix = random.randint(1000, 9999)
                    batch_num = f"BATCH{import_date.strftime('%Y%m%d')}{variant.id}{suffix}"
                    if batch_num not in used_numbers:
                        used_numbers.add(batch_num)
                        break
                else:
                    batch_num = f"BATCH{import_date.strftime('%Y%m%d')}{variant.id}{random.randint(10000,99999)}"
                    used_numbers.add(batch_num)

                MedicineBatch.objects.using("store").create(
                    batch_number=batch_num,
                    product_variant=variant,
                    import_date=import_date,
                    expiry_date=expiry_date,
                    quantity=quantity,
                    remaining_quantity=quantity,
                    import_price_per_base_unit=None,
                    active=True,
                )
                created += 1

            # Khớp cache tồn kho với nguồn sự thật = tổng batch (đơn vị cơ sở)
            sync_in_stock_cache(variant.id)

        return created

    # ----------------------------------------------------------
    # Print stats for 1 file
    # ----------------------------------------------------------
    def _print_file_stats(self, stats: dict):
        self.stdout.write(
            f"  rows={stats['rows']}  "
            f"product+={stats['products_created']} ~{stats['products_updated']}  "
            f"variant+={stats['variants_created']} ~{stats['variants_updated']}  "
            f"variantUnit+={stats.get('variant_units_created', 0)} ~{stats.get('variant_units_updated', 0)}  "
            f"brand+={stats['brands_created']}  "
            f"cat+={stats['categories_created']}  "
            f"batch+={stats['batches_created']}  "
            f"err={stats['errors']}"
        )
