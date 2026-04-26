"""
sync_mainapp_data.py
--------------------
Management command để đồng bộ dữ liệu từ mainApp sang storeApp.

Thứ tự sync (đúng thứ tự dependency):
  1. Brands   — lấy từ storeApp.Brand (đã có sẵn, chỉ cập nhật)
  2. Categories
  3. Products  (Medicine → Product, cần Brand & Category đã có)
  4. Variants  (MedicineUnit → ProductVariant, cần Product)
  5. Stats     (MedicineUnitStats → ProductVariantStats, cần Variant)

Optimisations:
  - select_related / prefetch_related để tránh N+1
  - bulk_update_or_create qua dict lookup thay vì vòng lặp ORM per-row
  - Dry-run: dùng transaction.set_rollback → không có side effect
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from mainApp.models import (
    Category as MainCategory,
    Medicine as MainMedicine,
    MedicineUnit as MainMedicineUnit,
    MedicineUnitStats as MainMedicineUnitStats,
)
from storeApp.models import (
    Brand as StoreBrand,
    Category as StoreCategory,
    Product as StoreProduct,
    ProductVariant as StoreProductVariant,
    ProductVariantUnit as StoreProductVariantUnit,
    ProductVariantStats as StoreProductVariantStats,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # chunk size khi bulk_create/update


class Command(BaseCommand):
    help = "Syncs data from mainApp to storeApp (Brands, Categories, Products, Variants, Stats)."

    # ------------------------------------------------------------------ #
    #  CLI arguments                                                        #
    # ------------------------------------------------------------------ #
    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data in storeApp trước sync (không xóa Brands/Vouchers).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Dry run — không lưu thay đổi vào DB.",
        )
        parser.add_argument(
            "--skip-brands",
            action="store_true",
            help="Bỏ qua bước sync Brands (mặc định Brands được cập nhật).",
        )

    # ------------------------------------------------------------------ #
    #  Entry point                                                          #
    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        clear_data = options["clear"]
        skip_brands = options["skip_brands"]

        if dry_run:
            self.stdout.write(self.style.WARNING("--- DRY-RUN MODE: mọi thay đổi sẽ bị rollback ---"))

        try:
            with transaction.atomic(using="store"):
                # --- Optional clear (không xóa Brand vì không được quản lý ở đây) ---
                if clear_data:
                    self._clear_store_data()

                # --- Sync theo thứ tự dependency ---
                if not skip_brands:
                    self.sync_brands()

                self.sync_categories()
                self.sync_products()
                self.sync_variants()
                self.sync_variant_units()
                self.sync_stats()

                if dry_run:
                    self.stdout.write(self.style.WARNING("--- DRY-RUN COMPLETE: rolling back ---"))
                    transaction.set_rollback(True, using="store")
                else:
                    self.stdout.write(self.style.SUCCESS("✓ Sync hoàn tất."))

        except Exception as exc:
            logger.exception("Lỗi trong quá trình sync.")
            self.stdout.write(self.style.ERROR(f"✗ Lỗi: {exc}"))
            raise

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #
    def _clear_store_data(self):
        self.stdout.write(self.style.WARNING("Xóa dữ liệu cũ trong storeApp (trừ Brand/Voucher)..."))
        StoreProductVariantStats.objects.using("store").all().delete()
        StoreProductVariantUnit.objects.using("store").all().delete()
        StoreProductVariant.objects.using("store").all().delete()
        StoreProduct.objects.using("store").all().delete()
        StoreCategory.objects.using("store").all().delete()

    def _log(self, label: str, created: int, updated: int):
        self.stdout.write(
            f"  {label}: {self.style.SUCCESS(str(created))} tạo mới, "
            f"{self.style.WARNING(str(updated))} cập nhật."
        )

    @staticmethod
    def _chunked(iterable, size):
        """Chia list thành các chunk có kích thước cố định."""
        for i in range(0, len(iterable), size):
            yield iterable[i : i + size]

    # ------------------------------------------------------------------ #
    #  1. Brands                                                            #
    # ------------------------------------------------------------------ #
    def sync_brands(self):
        """
        Brand ở storeApp là nguồn gốc — mainApp.Medicine chỉ lưu brand_id (raw FK).
        Bước này không tạo Brand mới mà chỉ log để xác nhận Brands đã tồn tại.
        Nếu cần tạo Brand từ nguồn khác, hãy dùng import_csv command.
        """
        self.stdout.write("Kiểm tra Brands...")
        brand_count = StoreBrand.objects.using("store").count()
        self.stdout.write(f"  Hiện có {brand_count} Brand(s) trong store DB.")

    # ------------------------------------------------------------------ #
    #  2. Categories                                                        #
    # ------------------------------------------------------------------ #
    def sync_categories(self):
        self.stdout.write("Syncing Categories...")

        main_cats = list(
            MainCategory.objects.all()
            .order_by("level", "id")  # parent trước, child sau
        )

        # Lấy tất cả existing store categories vào memory
        existing = {obj.id: obj for obj in StoreCategory.objects.using("store").all()}

        to_create, to_update = [], []

        for mc in main_cats:
            defaults = {
                "name": mc.name,
                "slug": mc.slug,
                "parent_id": mc.parent_id,
                "level": mc.level,
                "path": mc.path,
                "path_slug": mc.path_slug,
                "created_date": mc.created_date,
                "updated_date": mc.updated_date,
                "active": mc.active,
            }
            if mc.id in existing:
                obj = existing[mc.id]
                changed = False
                for field, val in defaults.items():
                    if getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    to_update.append(obj)
            else:
                to_create.append(StoreCategory(id=mc.id, **defaults))

        update_fields = ["name", "slug", "parent_id", "level", "path", "path_slug",
                         "created_date", "updated_date", "active"]

        for chunk in self._chunked(to_create, BATCH_SIZE):
            StoreCategory.objects.using("store").bulk_create(chunk, ignore_conflicts=False)
        for chunk in self._chunked(to_update, BATCH_SIZE):
            StoreCategory.objects.using("store").bulk_update(chunk, update_fields)

        self._log("Categories", len(to_create), len(to_update))

    # ------------------------------------------------------------------ #
    #  3. Products (Medicine → Product)                                     #
    # ------------------------------------------------------------------ #
    def sync_products(self):
        self.stdout.write("Syncing Products...")

        # Lấy medicine + unit đầu tiên để lấy category_id (tránh N+1)
        main_medicines = list(
            MainMedicine.objects.all()
            .prefetch_related("units")
        )

        existing = {obj.id: obj for obj in StoreProduct.objects.using("store").all()}

        to_create, to_update = [], []

        for mm in main_medicines:
            # category từ unit đầu tiên (đã prefetch)
            units = list(mm.units.all())
            first_unit = units[0] if units else None
            default_category_id = first_unit.category_id if first_unit else None

            defaults = {
                "name": mm.name,
                "mid": mm.mid,
                "slug": mm.slug,
                "web_name": mm.web_name,
                "description": mm.description,
                "ingredients": mm.ingredients,
                "usage": mm.usage,
                "dosage": mm.dosage,
                "adverse_effect": mm.adverse_effect,
                "careful": mm.careful,
                "preservation": mm.preservation,
                "brand_id": mm.brand_id,       # raw FK — Brand đã có sẵn trong store DB
                "category_id": default_category_id,
                "created_date": mm.created_date,
                "updated_date": mm.updated_date,
                "active": mm.active,
            }

            if mm.id in existing:
                obj = existing[mm.id]
                changed = False
                for field, val in defaults.items():
                    if getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    to_update.append(obj)
            else:
                to_create.append(StoreProduct(id=mm.id, **defaults))

        update_fields = [
            "name", "mid", "slug", "web_name", "description", "ingredients",
            "usage", "dosage", "adverse_effect", "careful", "preservation",
            "brand_id", "category_id", "created_date", "updated_date", "active",
        ]

        for chunk in self._chunked(to_create, BATCH_SIZE):
            StoreProduct.objects.using("store").bulk_create(chunk, ignore_conflicts=False)
        for chunk in self._chunked(to_update, BATCH_SIZE):
            StoreProduct.objects.using("store").bulk_update(chunk, update_fields)

        self._log("Products", len(to_create), len(to_update))

    # ------------------------------------------------------------------ #
    #  4. Variants (MedicineUnit → ProductVariant)                         #
    # ------------------------------------------------------------------ #
    def sync_variants(self):
        self.stdout.write("Syncing Product Variants...")

        # Prefetch medicine và tất cả units của từng medicine để tính is_default
        main_units = list(
            MainMedicineUnit.objects.all()
            .select_related("medicine")
            .prefetch_related("medicine__units")
        )

        # Build map: medicine_id → first unit id (để tính is_default, tránh N+1)
        first_unit_id_by_medicine: dict[int, int] = {}
        for mu in main_units:
            mid = mu.medicine_id
            if mid not in first_unit_id_by_medicine:
                # units đã được prefetch, lấy id nhỏ nhất theo thứ tự insert (giống .first())
                all_unit_ids = sorted(u.id for u in mu.medicine.units.all())
                first_unit_id_by_medicine[mid] = all_unit_ids[0] if all_unit_ids else mu.id

        existing = {obj.id: obj for obj in StoreProductVariant.objects.using("store").all()}

        to_create, to_update = [], []

        for mu in main_units:
            first_unit_id = first_unit_id_by_medicine.get(mu.medicine_id)
            variant_packing = mu.package_size or f"Variant-{mu.id}"

            defaults = {
                "product_id": mu.medicine_id,
                "packing": variant_packing,
                "sku": f"MU-{mu.id}",
                "in_stock": mu.in_stock,
                "image": mu.image,
                "images": mu.images,
                "registration_number": mu.registration_number,
                "base_unit": "unit",
                "packing_meta": {
                    "main_unit_id": mu.id,
                    "source": "mainApp.sync",
                    "is_primary_variant_of_product": mu.id == first_unit_id,
                },
                "product_ranking": mu.product_ranking,
                "is_published": mu.is_published,
                "is_hot": mu.is_hot,
                "created_date": mu.created_date,
                "updated_date": mu.updated_date,
                "active": mu.active,
            }

            if mu.id in existing:
                obj = existing[mu.id]
                changed = False
                for field, val in defaults.items():
                    if getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    to_update.append(obj)
            else:
                to_create.append(StoreProductVariant(id=mu.id, **defaults))

        update_fields = [
            "product_id", "packing", "sku", "in_stock", "image", "images",
            "registration_number", "base_unit", "packing_meta", "product_ranking",
            "is_published", "is_hot", "created_date", "updated_date", "active",
        ]

        for chunk in self._chunked(to_create, BATCH_SIZE):
            StoreProductVariant.objects.using("store").bulk_create(chunk, ignore_conflicts=False)
        for chunk in self._chunked(to_update, BATCH_SIZE):
            StoreProductVariant.objects.using("store").bulk_update(chunk, update_fields)

        self._log("ProductVariants", len(to_create), len(to_update))

    # ------------------------------------------------------------------ #
    #  5. Variant Units (MedicineUnit pricing -> ProductVariantUnit)       #
    # ------------------------------------------------------------------ #
    def sync_variant_units(self):
        self.stdout.write("Syncing Product Variant Units...")

        main_units = list(MainMedicineUnit.objects.all())
        existing_by_variant = {
            obj.variant_id: obj
            for obj in StoreProductVariantUnit.objects.using("store").filter(is_default=True)
        }

        to_create, to_update = [], []

        for mu in main_units:
            unit_name = (mu.package_size or "default")[:50]
            defaults = {
                "variant_id": mu.id,
                "quantity_in_base": 1,
                "unit_name": unit_name,
                "unit_order": 0,
                "price_value": mu.price_value or 0,
                "price_display": mu.price_display or None,
                "compare_at_price": mu.original_price_value,
                "is_default": True,
                "is_published": mu.is_published,
                "created_date": mu.created_date,
                "updated_date": mu.updated_date,
                "active": mu.active,
            }

            existing = existing_by_variant.get(mu.id)
            if existing:
                changed = False
                for field, val in defaults.items():
                    if getattr(existing, field) != val:
                        setattr(existing, field, val)
                        changed = True
                if changed:
                    to_update.append(existing)
            else:
                to_create.append(StoreProductVariantUnit(**defaults))

        update_fields = [
            "quantity_in_base", "unit_name", "unit_order", "price_value",
            "price_display", "compare_at_price", "is_default", "is_published",
            "created_date", "updated_date", "active",
        ]

        for chunk in self._chunked(to_create, BATCH_SIZE):
            StoreProductVariantUnit.objects.using("store").bulk_create(chunk, ignore_conflicts=False)
        for chunk in self._chunked(to_update, BATCH_SIZE):
            StoreProductVariantUnit.objects.using("store").bulk_update(chunk, update_fields)

        self._log("ProductVariantUnits", len(to_create), len(to_update))

    # ------------------------------------------------------------------ #
    #  6. Stats (MedicineUnitStats → ProductVariantStats)                  #
    # ------------------------------------------------------------------ #
    def sync_stats(self):
        self.stdout.write("Syncing Product Variant Stats...")

        main_stats = list(MainMedicineUnitStats.objects.all())

        # Keyed by variant_id (= unit_id)
        existing = {obj.variant_id: obj for obj in StoreProductVariantStats.objects.using("store").all()}

        to_create, to_update = [], []

        for ms in main_stats:
            defaults = {
                "sold_total": ms.sold_total,
                "sold_30d": ms.sold_30d,
                "sold_7d": ms.sold_7d,
                "view_count": ms.view_count,
                "wishlist_count": ms.wishlist_count,
                # updated_at: auto_now → không cần set thủ công
            }

            if ms.unit_id in existing:
                obj = existing[ms.unit_id]
                changed = False
                for field, val in defaults.items():
                    if getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    to_update.append(obj)
            else:
                to_create.append(
                    StoreProductVariantStats(variant_id=ms.unit_id, **defaults)
                )

        update_fields = ["sold_total", "sold_30d", "sold_7d", "view_count", "wishlist_count"]

        for chunk in self._chunked(to_create, BATCH_SIZE):
            StoreProductVariantStats.objects.using("store").bulk_create(chunk, ignore_conflicts=False)
        for chunk in self._chunked(to_update, BATCH_SIZE):
            StoreProductVariantStats.objects.using("store").bulk_update(chunk, update_fields)

        self._log("ProductVariantStats", len(to_create), len(to_update))

