"""
Seed / upsert voucher data (shipping + order discount).

Usage:
  python manage.py store_import_vouchers                  # seed tất cả
  python manage.py store_import_vouchers --dry-run        # chỉ preview, không ghi DB
  python manage.py store_import_vouchers --scope shipping # chỉ SHIPPING_DISCOUNT
  python manage.py store_import_vouchers --scope order    # chỉ ORDER_DISCOUNT
  python manage.py store_import_vouchers --deactivate-unlisted  # is_active=False cho voucher cũ không có trong danh sách

Idempotent: dùng get_or_create theo `code`, chạy lại nhiều lần an toàn.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from storeApp.models import Voucher


def _voucher_definitions() -> list[dict]:
    """
    Single source of truth cho toàn bộ voucher seed.
    Thêm / sửa / xóa voucher ở đây rồi chạy lại command.
    """
    return [
        # ──────────────────────────────────────────────
        # SHIPPING_DISCOUNT — giảm phí ship
        # ──────────────────────────────────────────────
        {
            "code": "FREESHIP15K",
            "type": "FIXED",
            "scope": Voucher.SHIPPING_DISCOUNT,
            "value": Decimal("15000"),
            "max_discount": None,
            "min_order_value": Decimal("150000"),
            "description": "Giảm 15k phí ship cho đơn từ 150k",
            "usage_limit": 500,
            "per_user_limit": 3,
            "days_active": 90,
        },
        {
            "code": "FREESHIP30K",
            "type": "FIXED",
            "scope": Voucher.SHIPPING_DISCOUNT,
            "value": Decimal("30000"),
            "max_discount": None,
            "min_order_value": Decimal("250000"),
            "description": "Giảm 30k phí ship cho đơn từ 250k",
            "usage_limit": 200,
            "per_user_limit": 2,
            "days_active": 60,
        },
        {
            "code": "SHIPOFF50",
            "type": "PERCENT",
            "scope": Voucher.SHIPPING_DISCOUNT,
            "value": Decimal("50"),
            "max_discount": Decimal("25000"),
            "min_order_value": Decimal("200000"),
            "description": "Giảm 50% phí ship (tối đa 25k) cho đơn từ 200k",
            "usage_limit": 300,
            "per_user_limit": 2,
            "days_active": 45,
        },
        {
            "code": "SHIPOFF100",
            "type": "PERCENT",
            "scope": Voucher.SHIPPING_DISCOUNT,
            "value": Decimal("100"),
            "max_discount": Decimal("40000"),
            "min_order_value": Decimal("500000"),
            "description": "Miễn phí ship (tối đa 40k) cho đơn từ 500k",
            "usage_limit": 100,
            "per_user_limit": 1,
            "days_active": 30,
        },

        # ──────────────────────────────────────────────
        # ORDER_DISCOUNT — giảm giá đơn hàng (FIXED)
        # ──────────────────────────────────────────────
        {
            "code": "GIAM10K",
            "type": "FIXED",
            "scope": Voucher.ORDER_DISCOUNT,
            "value": Decimal("10000"),
            "max_discount": None,
            "min_order_value": Decimal("100000"),
            "description": "Giảm 10k cho đơn từ 100k",
            "usage_limit": 1000,
            "per_user_limit": 5,
            "days_active": 90,
        },
        {
            "code": "GIAM30K",
            "type": "FIXED",
            "scope": Voucher.ORDER_DISCOUNT,
            "value": Decimal("30000"),
            "max_discount": None,
            "min_order_value": Decimal("300000"),
            "description": "Giảm 30k cho đơn từ 300k",
            "usage_limit": 500,
            "per_user_limit": 3,
            "days_active": 60,
        },
        {
            "code": "GIAM50K",
            "type": "FIXED",
            "scope": Voucher.ORDER_DISCOUNT,
            "value": Decimal("50000"),
            "max_discount": None,
            "min_order_value": Decimal("500000"),
            "description": "Giảm 50k cho đơn từ 500k",
            "usage_limit": 200,
            "per_user_limit": 2,
            "days_active": 45,
        },

        # ──────────────────────────────────────────────
        # ORDER_DISCOUNT — giảm giá đơn hàng (PERCENT)
        # ──────────────────────────────────────────────
        {
            "code": "SALE5",
            "type": "PERCENT",
            "scope": Voucher.ORDER_DISCOUNT,
            "value": Decimal("5"),
            "max_discount": Decimal("30000"),
            "min_order_value": Decimal("150000"),
            "description": "Giảm 5% (tối đa 30k) cho đơn từ 150k",
            "usage_limit": 800,
            "per_user_limit": 5,
            "days_active": 90,
        },
        {
            "code": "SALE10",
            "type": "PERCENT",
            "scope": Voucher.ORDER_DISCOUNT,
            "value": Decimal("10"),
            "max_discount": Decimal("50000"),
            "min_order_value": Decimal("200000"),
            "description": "Giảm 10% (tối đa 50k) cho đơn từ 200k",
            "usage_limit": 400,
            "per_user_limit": 3,
            "days_active": 60,
        },
        {
            "code": "SALE15",
            "type": "PERCENT",
            "scope": Voucher.ORDER_DISCOUNT,
            "value": Decimal("15"),
            "max_discount": Decimal("80000"),
            "min_order_value": Decimal("400000"),
            "description": "Giảm 15% (tối đa 80k) cho đơn từ 400k",
            "usage_limit": 150,
            "per_user_limit": 2,
            "days_active": 30,
        },
        {
            "code": "NEWUSER20",
            "type": "PERCENT",
            "scope": Voucher.ORDER_DISCOUNT,
            "value": Decimal("20"),
            "max_discount": Decimal("100000"),
            "min_order_value": Decimal("300000"),
            "description": "Khách mới giảm 20% (tối đa 100k) cho đơn từ 300k",
            "usage_limit": 1000,
            "per_user_limit": 1,
            "days_active": 180,
        },
    ]


def _format_label(d: dict) -> str:
    if d["type"] == "PERCENT":
        cap = f" (cap {d['max_discount']:,.0f}₫)" if d["max_discount"] else ""
        return f"{d['value']}%{cap}"
    return f"{d['value']:,.0f}₫"


class Command(BaseCommand):
    help = "Seed / upsert voucher data (shipping + order discount). Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview only — no DB writes.",
        )
        parser.add_argument(
            "--scope",
            choices=["shipping", "order", "all"],
            default="all",
            help="Filter by voucher scope (default: all).",
        )
        parser.add_argument(
            "--deactivate-unlisted",
            action="store_true",
            help="Set is_active=False for existing vouchers whose code is NOT in the definitions list.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        scope_filter = options["scope"]
        deactivate = options["deactivate_unlisted"]

        now = timezone.now()
        definitions = _voucher_definitions()

        if scope_filter == "shipping":
            definitions = [d for d in definitions if d["scope"] == Voucher.SHIPPING_DISCOUNT]
        elif scope_filter == "order":
            definitions = [d for d in definitions if d["scope"] == Voucher.ORDER_DISCOUNT]

        created_count = 0
        skipped_count = 0
        defined_codes = set()

        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY-RUN] ' if dry_run else ''}Seeding {len(definitions)} voucher(s)..."
        ))

        for d in definitions:
            defined_codes.add(d["code"])
            label = _format_label(d)

            if dry_run:
                self.stdout.write(f"  [dry] {d['code']:16s}  {d['scope']:18s}  {label:>20s}  min={d['min_order_value']:>10,.0f}₫")
                created_count += 1
                continue

            _, created = Voucher.objects.get_or_create(
                code=d["code"],
                defaults={
                    "type": d["type"],
                    "scope": d["scope"],
                    "value": d["value"],
                    "max_discount": d["max_discount"],
                    "min_order_value": d["min_order_value"],
                    "description": d["description"],
                    "usage_limit": d["usage_limit"],
                    "per_user_limit": d["per_user_limit"],
                    "start_at": now,
                    "end_at": now + timedelta(days=d["days_active"]),
                    "is_active": True,
                    "applicable_products": [],
                    "applicable_categories": [],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  + {d['code']:16s}  {d['scope']:18s}  {label}")
            else:
                skipped_count += 1
                self.stdout.write(f"  = {d['code']:16s}  (already exists, skipped)")

        if deactivate and not dry_run:
            stale = Voucher.objects.filter(is_active=True).exclude(code__in=defined_codes)
            stale_count = stale.count()
            if stale_count:
                stale.update(is_active=False)
                self.stdout.write(self.style.WARNING(f"  Deactivated {stale_count} unlisted voucher(s)."))

        tag = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{tag}Done. created={created_count}, skipped={skipped_count}, "
            f"total_in_db={Voucher.objects.count()}"
        ))
