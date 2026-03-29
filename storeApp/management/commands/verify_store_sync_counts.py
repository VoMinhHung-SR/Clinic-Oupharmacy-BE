"""
Đối soát nhanh số bản ghi mainApp (default) vs storeApp (alias store) sau sync.

Dùng cho wave đối soát trong kế hoạch migrate: Category, Product/Medicine, Variant/Unit,
Stats, Voucher. ProductVariantUnit trên store nên khớp số MedicineUnit nếu đã chạy sync_variant_units.

  python manage.py verify_store_sync_counts
  python manage.py verify_store_sync_counts --json
"""
import json

from django.core.management.base import BaseCommand

from mainApp.models import (
    Category as MainCategory,
    Medicine as MainMedicine,
    MedicineUnit as MainMedicineUnit,
    MedicineUnitStats as MainMedicineUnitStats,
    Voucher as MainVoucher,
)
from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import (
    Category as StoreCategory,
    Product as StoreProduct,
    ProductVariant as StoreProductVariant,
    ProductVariantUnit as StoreProductVariantUnit,
    ProductVariantStats as StoreProductVariantStats,
    Voucher as StoreVoucher,
)


def _count(qs):
    return qs.count()


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

        rows = [
            {
                "entity": "Category",
                "main": _count(MainCategory.objects.all()),
                "store": _count(StoreCategory.objects.using(STORE_DATABASE_ALIAS).all()),
            },
            {
                "entity": "Product / Medicine",
                "main": _count(MainMedicine.objects.all()),
                "store": _count(StoreProduct.objects.using(STORE_DATABASE_ALIAS).all()),
            },
            {
                "entity": "ProductVariant / MedicineUnit",
                "main": _count(MainMedicineUnit.objects.all()),
                "store": _count(StoreProductVariant.objects.using(STORE_DATABASE_ALIAS).all()),
            },
            {
                "entity": "ProductVariantUnit (store only mapping)",
                "main": _count(MainMedicineUnit.objects.all()),
                "store": _count(StoreProductVariantUnit.objects.using(STORE_DATABASE_ALIAS).all()),
                "note": "store should match MedicineUnit count after sync_variant_units",
            },
            {
                "entity": "ProductVariantStats / MedicineUnitStats",
                "main": _count(MainMedicineUnitStats.objects.all()),
                "store": _count(StoreProductVariantStats.objects.using(STORE_DATABASE_ALIAS).all()),
            },
            {
                "entity": "Voucher",
                "main": _count(MainVoucher.objects.all()),
                "store": _count(StoreVoucher.objects.using(STORE_DATABASE_ALIAS).all()),
            },
        ]

        if as_json:
            self.stdout.write(json.dumps(rows, indent=2, ensure_ascii=False))
            return

        self.stdout.write(self.style.NOTICE("mainApp (default) vs storeApp (store) — record counts"))
        self.stdout.write("")
        mismatches = 0
        for r in rows:
            main_c = r["main"]
            store_c = r["store"]
            ok = main_c == store_c
            if not ok:
                mismatches += 1
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
