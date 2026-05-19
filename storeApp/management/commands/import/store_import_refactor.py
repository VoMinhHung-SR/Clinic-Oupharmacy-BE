"""
store_import_refactor.py
------------------------
One-shot catalog refactor: gọi store_import_csv với preset đúng cho old → new workflow.

Dry-run mặc định (không ghi DB). Dùng --apply để import thật.

Ví dụ:
  # Smoke: 1 file CSV nhỏ nhất trong data/old (2 dòng data)
  python manage.py store_import_refactor --dry-run --sample

  # Toàn bộ data/old (packageOptions refactor + batch simulated)
  python manage.py store_import_refactor --dry-run

  # Old rồi new (2 phase)
  python manage.py store_import_refactor --dry-run --phase both

  # Ghi DB
  python manage.py store_import_refactor --apply --phase both --update-existing
"""

from __future__ import annotations

import csv
import os
from typing import Optional

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

DEFAULT_OLD_DIR = "storeApp/test/data/old"
DEFAULT_NEW_DIR = "storeApp/test/data/new"


def _abs_path(rel: str) -> str:
    if os.path.isabs(rel):
        return rel
    return os.path.join(str(settings.BASE_DIR), rel)


def _iter_csv_files(root: str) -> list[str]:
    files = []
    for dirpath, _, filenames in os.walk(root):
        for name in sorted(filenames):
            if name.endswith(".csv"):
                files.append(os.path.join(dirpath, name))
    return files


def _count_csv_data_rows(csv_path: str) -> int:
    with open(csv_path, encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


def _find_smallest_csv(root: str) -> Optional[str]:
    candidates = _iter_csv_files(root)
    if not candidates:
        return None
    return min(candidates, key=_count_csv_data_rows)


class Command(BaseCommand):
    help = (
        "Refactor import one-shot: old/new CSV paths, --dry-run + --update-existing + batch logic. "
        "Mặc định dry-run; --apply để ghi DB."
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Không ghi DB (mặc định nếu không có --apply).",
        )
        mode.add_argument(
            "--apply",
            action="store_true",
            help="Ghi DB (tắt dry-run).",
        )

        parser.add_argument(
            "--update-existing",
            action="store_true",
            default=True,
            help="Upsert product/variant/unit nếu đã có (mặc định bật).",
        )
        parser.add_argument(
            "--no-update-existing",
            action="store_false",
            dest="update_existing",
            help="Chỉ tạo mới, không cập nhật bản ghi đã tồn tại.",
        )

        parser.add_argument(
            "--phase",
            choices=("old", "new", "both"),
            default="old",
            help="old=packageOptions refactor; new=saleUnits; both=old rồi new.",
        )
        parser.add_argument(
            "--path",
            default=None,
            help="Override thư mục/file CSV (bỏ qua --phase default path).",
        )
        parser.add_argument(
            "--category",
            default=None,
            help="Lọc thư mục con, vd thuc-pham-chuc-nang, thuoc, duoc-mi-pham.",
        )
        parser.add_argument(
            "--sample",
            action="store_true",
            help="Chỉ chạy 1 file CSV có ít dòng nhất (smoke test).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Giới hạn rows mỗi file (truyền sang store_import_csv).",
        )
        parser.add_argument(
            "--no-batches",
            action="store_true",
            help="Bỏ tạo/simulate MedicineBatch.",
        )
        parser.add_argument(
            "--batch-pack-mult-min",
            type=int,
            default=None,
            help="Truyền sang store_import_csv (default giữ trong importer).",
        )
        parser.add_argument(
            "--batch-pack-mult-max",
            type=int,
            default=None,
            help="Truyền sang store_import_csv (default giữ trong importer).",
        )
        parser.add_argument(
            "--batch-count",
            type=int,
            default=None,
            help="Số batch mỗi variant.",
        )
        parser.add_argument(
            "--no-smart-random-price",
            action="store_true",
            help="Tắt random giá theo tier đơn vị (dùng random phẳng).",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Chỉ dùng một trong --dry-run hoặc --apply.")
        # Mặc định dry-run khi không truyền --apply
        dry_run = not options["apply"]
        phases = self._resolve_phases(options["phase"])

        if options["path"]:
            paths = [("custom", _abs_path(options["path"]))]
        else:
            paths = []
            for phase in phases:
                base = DEFAULT_OLD_DIR if phase == "old" else DEFAULT_NEW_DIR
                root = _abs_path(base)
                if options["category"]:
                    root = os.path.join(root, options["category"])
                if not os.path.isdir(root) and not os.path.isfile(root):
                    raise CommandError(f"Không tìm thấy path: {root}")
                paths.append((phase, root))

        self.stdout.write(self.style.MIGRATE_HEADING("store_import_refactor"))
        self.stdout.write(
            f"  mode={'DRY-RUN' if dry_run else 'APPLY'}  "
            f"update_existing={options['update_existing']}  "
            f"batches={'off' if options['no_batches'] else 'on'}"
        )

        for phase_label, import_path in paths:
            if options["sample"]:
                smallest = _find_smallest_csv(import_path)
                if not smallest:
                    raise CommandError(f"Không có CSV trong: {import_path}")
                row_count = _count_csv_data_rows(smallest)
                self.stdout.write(
                    self.style.WARNING(
                        f"\n▶ Phase [{phase_label}] SAMPLE — {os.path.relpath(smallest, settings.BASE_DIR)} "
                        f"({row_count} rows)"
                    )
                )
                import_path = smallest
            else:
                self.stdout.write(
                    self.style.WARNING(f"\n▶ Phase [{phase_label}] — {import_path}")
                )

            kwargs = {
                "dry_run": dry_run,
                "update_existing": options["update_existing"],
                "no_batches": options["no_batches"],
            }
            if options["limit"] is not None:
                kwargs["limit"] = options["limit"]
            if options["batch_pack_mult_min"] is not None:
                kwargs["batch_pack_mult_min"] = options["batch_pack_mult_min"]
            if options["batch_pack_mult_max"] is not None:
                kwargs["batch_pack_mult_max"] = options["batch_pack_mult_max"]
            if options["batch_count"] is not None:
                kwargs["batch_count"] = options["batch_count"]
            if options["no_smart_random_price"]:
                kwargs["no_smart_random_price"] = True

            call_command("store_import_csv", import_path, **kwargs)

        self.stdout.write(self.style.SUCCESS("\n✅ store_import_refactor hoàn tất."))
        if dry_run:
            self.stdout.write(
                "   Ghi DB: python manage.py store_import_refactor --apply "
                f"--phase {options['phase']} --update-existing"
            )

    @staticmethod
    def _resolve_phases(phase: str) -> list[str]:
        if phase == "both":
            return ["old", "new"]
        return [phase]
