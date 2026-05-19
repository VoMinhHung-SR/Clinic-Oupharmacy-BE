"""
So sánh 1 Product trong DB (store) với row scrape [new] CSV — trước khi import phase old.

Usage:
  cd Clinic-Oupharmacy-BE

  # Tổng quan catalog DB
  python manage.py store_audit_product --overview

  # So sánh theo mid (basicInfo.sku)
  python manage.py store_audit_product --mid 00002393

  # So sánh theo slug
  python manage.py store_audit_product --slug diabetna-vien-uong-ha-duong-huyet-mo-mau-370

  # Chỉ định file CSV new (mặc định quét storeApp/test/data/new)
  python manage.py store_audit_product --mid 00002393 --scrape-root storeApp/test/data/new
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q

from storeApp.models import MedicineBatch, Product, ProductVariant, ProductVariantUnit

# Schema tham chiếu refactor (core: base_unit, price, quantity_in_base) — keys only, no sample data.
REFACTOR_PAYLOAD_SCHEMA = {
    "product": {
        "mid": "string (basicInfo.sku, unique)",
        "slug": "string",
        "name": "string",
        "web_name": "string|null",
        "brand": "string|null",
        "category_slug": "string|null",
        "content": {
            "description": "html|string|null",
            "ingredients": "text|null",
            "usage": "html|string|null",
            "dosage": "html|string|null",
            "adverse_effect": "html|string|null",
            "careful": "html|string|null",
            "preservation": "html|string|null",
        },
    },
    "variant": {
        "packing": "string (pricing.packageSize)",
        "base_unit": "string (unit with min quantity_in_base; e.g. Viên)",
        "sku": "string|null (unique when set; usually same as mid once)",
        "packing_meta": {
            "origin": "string",
            "manufacturer": "string",
            "shelf_life": "string",
            "units": "string[] (unit names, denormalized)",
        },
        "in_stock": "integer (cache, base units)",
        "is_published": "boolean",
    },
    "units": [
        {
            "unit_name": "string (saleUnits.unitName | packageOptions)",
            "quantity_in_base": "integer >= 1 (saleUnits.quantityInBase)",
            "price_value": "decimal VND (saleUnits.priceValue)",
            "price_display": "string (saleUnits.priceDisplay)",
            "is_default": "boolean (saleUnits.isDefault)",
            "unit_order": "integer (saleUnits.unitOrder)",
        }
    ],
    "batch": {
        "quantity": "integer (MedicineBatch, đơn vị cơ sở)",
        "remaining_quantity": "integer",
        "import_price_per_base_unit": "decimal|null (price_value / default_unit.quantity_in_base)",
    },
    "scrape_sources": {
        "new": "pricing.saleUnits[] (preferred)",
        "old": "pricing.packageOptions (fallback, heuristic quantity_in_base)",
    },
}


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


def _abs_path(rel: str) -> str:
    if os.path.isabs(rel):
        return rel
    return os.path.join(str(settings.BASE_DIR), rel)


def _find_csv_row_by_mid(scrape_root: str, mid: str) -> Optional[tuple[str, dict]]:
    mid = str(mid).strip()
    for dirpath, _, filenames in os.walk(scrape_root):
        for name in sorted(filenames):
            if not name.endswith(".csv"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if str(row.get("basicInfo.sku") or "").strip() == mid:
                        return path, row
    return None


def _trunc(val, n=80) -> str:
    s = str(val or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 3] + "..."


class Command(BaseCommand):
    help = "Audit DB product vs new scrape CSV schema (pre-import check)."

    def add_arguments(self, parser):
        parser.add_argument("--overview", action="store_true", help="Thống kê catalog DB store.")
        parser.add_argument("--mid", help="basicInfo.sku / Product.mid")
        parser.add_argument("--slug", help="basicInfo.slug / Product.slug")
        parser.add_argument(
            "--scrape-root",
            default="storeApp/test/data/new",
            help="Thư mục CSV scrape (default: storeApp/test/data/new).",
        )
        parser.add_argument(
            "--payload-only",
            action="store_true",
            help="Chỉ in JSON payload DB (lookup shape) khi dùng --mid/--slug.",
        )

    def handle(self, *args, **options):
        if options["overview"]:
            self._print_overview()
            self._print_refactor_schema()
            if not options["mid"] and not options["slug"]:
                self.stdout.write(
                    "\nTip: python manage.py store_audit_product --mid <sku> [--payload-only]"
                )
                return

        if not options["mid"] and not options["slug"]:
            raise CommandError("Cần --overview và/hoặc --mid / --slug.")

        if options["mid"] or options["slug"]:
            self._compare_one(
                mid=options.get("mid"),
                slug=options.get("slug"),
                scrape_root=_abs_path(options["scrape_root"]),
                payload_only=options["payload_only"],
            )

    def _print_overview(self):
        using = "store"
        self.stdout.write(self.style.MIGRATE_HEADING("Store catalog overview (DB alias: store)"))

        products = Product.objects.using(using).count()
        variants = ProductVariant.objects.using(using).count()
        units = ProductVariantUnit.objects.using(using).count()
        batches = MedicineBatch.objects.using(using).count()
        zero_price_units = ProductVariantUnit.objects.using(using).filter(price_value__lte=0).count()
        no_default = (
            ProductVariant.objects.using(using)
            .annotate(dc=Count("units", filter=Q(units__is_default=True)))
            .filter(dc=0)
            .count()
        )

        self.stdout.write(f"  Products          : {products}")
        self.stdout.write(f"  Variants          : {variants}")
        self.stdout.write(f"  VariantUnits      : {units}")
        self.stdout.write(f"  MedicineBatches   : {batches}")
        self.stdout.write(f"  Units price <= 0  : {zero_price_units}")
        self.stdout.write(f"  Variants no default unit : {no_default}")

        sample = (
            Product.objects.using(using)
            .filter(mid__isnull=False)
            .exclude(mid="")
            .order_by("-updated_date")[:5]
        )
        if sample:
            self.stdout.write("\n  Sample mids (recent):")
            for p in sample:
                self.stdout.write(f"    · {p.mid}  {p.slug}")

    def _print_refactor_schema(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nRefactor payload schema (keys only)"))
        self.stdout.write(json.dumps(REFACTOR_PAYLOAD_SCHEMA, indent=2, ensure_ascii=False))

    @staticmethod
    def _build_db_payload(product: Product, variants: list) -> dict:
        """Canonical lookup shape after import (cart/API cares about units[]."""
        variant_payloads = []
        for v in variants:
            units = list(v.units.all().order_by("unit_order", "id"))
            batches = list(v.batches.filter(active=True))
            batch_sum = sum(b.remaining_quantity for b in batches)
            variant_payloads.append({
                "variant_id": v.id,
                "packing": v.packing,
                "base_unit": v.base_unit,
                "sku": v.sku,
                "packing_meta": v.packing_meta or {},
                "in_stock": v.in_stock,
                "is_published": v.is_published,
                "units": [
                    {
                        "unit_id": u.id,
                        "unit_name": u.unit_name,
                        "quantity_in_base": u.quantity_in_base,
                        "price_value": float(u.price_value or 0),
                        "price_display": u.price_display,
                        "is_default": u.is_default,
                        "unit_order": u.unit_order,
                    }
                    for u in units
                ],
                "batches_summary": {
                    "count": len(batches),
                    "remaining_quantity_sum": batch_sum,
                },
            })
        return {
            "product": {
                "id": product.id,
                "mid": product.mid,
                "slug": product.slug,
                "name": product.name,
                "web_name": product.web_name,
                "brand": product.brand.name if product.brand_id else None,
                "category_slug": product.category.path_slug if product.category_id else None,
                "content": {
                    "description": _content_shape(product.description),
                    "ingredients": _content_shape(product.ingredients),
                    "usage": _content_shape(product.usage),
                    "dosage": _content_shape(product.dosage),
                    "adverse_effect": _content_shape(product.adverse_effect),
                    "careful": _content_shape(product.careful),
                    "preservation": _content_shape(product.preservation),
                },
            },
            "variants": variant_payloads,
        }

    def _compare_one(
        self,
        mid: Optional[str],
        slug: Optional[str],
        scrape_root: str,
        payload_only: bool = False,
    ):
        using = "store"
        product = None
        if mid:
            product = Product.objects.using(using).filter(mid=str(mid).strip()).first()
        if not product and slug:
            product = Product.objects.using(using).filter(slug=str(slug).strip()).first()

        if not product:
            raise CommandError(f"Không tìm thấy Product trong DB (mid={mid!r}, slug={slug!r}).")

        lookup_mid = product.mid or mid
        csv_hit = _find_csv_row_by_mid(scrape_root, lookup_mid) if lookup_mid else None

        self.stdout.write(self.style.MIGRATE_HEADING(f"Product id={product.id} mid={product.mid}"))
        self.stdout.write(f"  name      : {_trunc(product.name, 100)}")
        self.stdout.write(f"  slug      : {product.slug}")
        self.stdout.write(f"  brand     : {product.brand.name if product.brand_id else '-'}")
        self.stdout.write(
            f"  category  : {product.category.path_slug if product.category_id else '-'}"
        )

        variants = list(
            ProductVariant.objects.using(using)
            .filter(product=product)
            .prefetch_related("units", "batches")
        )

        db_payload = self._build_db_payload(product, variants)
        if payload_only:
            self.stdout.write(json.dumps(db_payload, indent=2, ensure_ascii=False))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("\nDB payload (lookup / refactor core)"))
        self.stdout.write(json.dumps(db_payload, indent=2, ensure_ascii=False))

        self.stdout.write(f"\n  Variants in DB: {len(variants)}")
        for v in variants:
            units = list(v.units.all().order_by("unit_order", "id"))
            batch_qty = sum(b.remaining_quantity for b in v.batches.filter(active=True))
            self.stdout.write(
                f"\n  --- Variant id={v.id} packing={v.packing!r} base_unit={v.base_unit!r} "
                f"in_stock={v.in_stock} batches_remaining_sum={batch_qty}"
            )
            meta = v.packing_meta or {}
            self.stdout.write(
                f"      packing_meta: origin={_trunc(meta.get('origin'))} "
                f"mfr={_trunc(meta.get('manufacturer'), 40)} shelf={meta.get('shelf_life')}"
            )
            for u in units:
                self.stdout.write(
                    f"      unit id={u.id} {u.unit_name!r} qib={u.quantity_in_base} "
                    f"price={u.price_value} default={u.is_default} order={u.unit_order}"
                )

        if not csv_hit:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠ Không có row [new] CSV cho mid={lookup_mid!r} under {scrape_root}"
                )
            )
            self.stdout.write("  (Sản phẩm có thể chỉ có trong data/old — phase old sẽ dùng packageOptions.)")
            return

        csv_path, row = csv_hit
        self.stdout.write(self.style.SUCCESS(f"\n✓ CSV [new]: {os.path.relpath(csv_path, settings.BASE_DIR)}"))

        sale_units = _parse_json_field(row.get("pricing.saleUnits"), default=[])
        self.stdout.write(self.style.MIGRATE_HEADING("\nField checklist (DB vs scrape [new])"))

        checks = [
            ("basicInfo.name", product.name, row.get("basicInfo.name")),
            ("basicInfo.slug", product.slug, row.get("basicInfo.slug")),
            ("basicInfo.webName", product.web_name, row.get("basicInfo.webName")),
            ("content.description", _has_text(product.description), _has_text(row.get("content.description"))),
            ("content.ingredients", _has_text(product.ingredients), _has_text(row.get("content.ingredients"))),
            ("pricing.saleUnits", self._db_has_units(variants), len(sale_units) > 0),
            ("pricing.saleUnits count", self._db_unit_count(variants), len(sale_units)),
        ]
        for label, db_val, csv_val in checks:
            ok = "✓" if _values_align(db_val, csv_val, label) else "✗"
            self.stdout.write(f"  {ok} {label:28} DB={db_val!r}  CSV={csv_val!r}")

        if sale_units:
            self.stdout.write("\n  saleUnits (CSV):")
            for su in sale_units:
                if not isinstance(su, dict):
                    continue
                self.stdout.write(
                    f"    · {su.get('unitName')!r} qib={su.get('quantityInBase')} "
                    f"price={su.get('priceValue')} default={su.get('isDefault')}"
                )

        self.stdout.write(
            "\n"
            "Ghi chú schema:\n"
            "  · Importer [new] map saleUnits → ProductVariantUnit (unit_name, quantity_in_base, price_*).\n"
            "  · origin/manufacturer/shelf_life → ProductVariant.packing_meta (không Product.origin).\n"
            "  · registrationNumber → non-import (SKIP).\n"
            "  · Phase old dùng packageOptions nếu không có saleUnits trong CSV."
        )

    @staticmethod
    def _db_has_units(variants) -> bool:
        return any(v.units.exists() for v in variants)

    @staticmethod
    def _db_unit_count(variants) -> int:
        return sum(v.units.count() for v in variants)


def _has_text(val) -> bool:
    return bool(str(val or "").strip())


def _content_shape(val) -> str:
    if not _has_text(val):
        return "empty"
    text = str(val).strip()
    if "<" in text and ">" in text:
        return f"html ({len(text)} chars)"
    return f"text ({len(text)} chars)"


def _values_align(db_val, csv_val, label: str) -> bool:
    if "count" in label.lower():
        try:
            return int(db_val) == int(csv_val)
        except (TypeError, ValueError):
            return False
    if label.startswith("content."):
        return bool(db_val) == bool(csv_val)
    if isinstance(db_val, str) and isinstance(csv_val, str):
        return db_val.strip() == csv_val.strip()
    return db_val == csv_val
