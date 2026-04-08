"""
Đối soát nhanh số bản ghi mainApp (default) vs storeApp (alias store) sau sync.

Dùng cho wave đối soát trong kế hoạch migrate: Category, Product/Medicine, Variant/Unit,
Stats, Voucher. ProductVariantUnit trên store nên khớp số MedicineUnit nếu đã chạy sync_variant_units.

  python manage.py verify_store_sync_counts
  python manage.py verify_store_sync_counts --json
"""
import json

from django.apps import apps
from django.core.management.base import BaseCommand

from storeApp.constants import STORE_DATABASE_ALIAS


def _count(qs):
    return qs.count()


def _model_or_none(app_label, model_name):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _main_count_or_none(app_label, model_name):
    model = _model_or_none(app_label, model_name)
    if model is None:
        return None
    return _count(model.objects.all())


def _store_count_or_none(model_name):
    model = _model_or_none("storeApp", model_name)
    if model is None:
        return None
    return _count(model.objects.using(STORE_DATABASE_ALIAS).all())


class Command(BaseCommand):
    help = "Compare record counts between mainApp (default DB) and storeApp (store DB) for migration verification."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON instead of table text.",
        )

    def handle(self, *args, **options):
        as_json = options["json"]
        mappings = [
            ("Category", "Category", "Category", None),
            ("Product / Medicine", "Medicine", "Product", None),
            ("ProductVariant / MedicineUnit", "MedicineUnit", "ProductVariant", None),
            (
                "ProductVariantUnit (store only mapping)",
                "MedicineUnit",
                "ProductVariantUnit",
                "store should match MedicineUnit count after sync_variant_units",
            ),
            ("ProductVariantStats / MedicineUnitStats", "MedicineUnitStats", "ProductVariantStats", None),
            ("Voucher", "Voucher", "Voucher", None),
        ]
        rows = []
        for entity, main_model, store_model, note in mappings:
            row = {
                "entity": entity,
                "main": _main_count_or_none("mainApp", main_model),
                "store": _store_count_or_none(store_model),
            }
            if note:
                row["note"] = note
            rows.append(row)

        if as_json:
            self.stdout.write(json.dumps(rows, indent=2, ensure_ascii=False))
            return

        self.stdout.write(self.style.NOTICE("mainApp (default) vs storeApp (store) — record counts"))
        self.stdout.write("")
        mismatches = 0
        for r in rows:
            main_c = r["main"]
            store_c = r["store"]
            comparable = main_c is not None
            ok = comparable and main_c == store_c
            if comparable and not ok:
                mismatches += 1
            if not comparable:
                status = self.style.WARNING("N/A")
                line = f"  [{status}] {r['entity']}: main=<model missing>  store={store_c}"
            elif store_c is None:
                status = self.style.WARNING("N/A")
                line = f"  [{status}] {r['entity']}: main={main_c}  store=<model missing>"
            else:
                status = self.style.SUCCESS("OK") if ok else self.style.WARNING("MISMATCH")
                line = f"  [{status}] {r['entity']}: main={main_c}  store={store_c}"
            if "note" in r:
                line += f"  ({r['note']})"
            self.stdout.write(line)

        self.stdout.write("")
        if mismatches:
            self.stdout.write(
                self.style.WARNING(
                    f"Found {mismatches} row(s) with unequal main/store counts — run sync or investigate."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("All comparable counts match."))
