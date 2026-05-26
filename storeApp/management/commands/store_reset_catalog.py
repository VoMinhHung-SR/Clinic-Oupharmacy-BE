"""
Làm sạch dữ liệu storeApp (DB `store`) trước khi import lại CSV — có thứ tự FK rõ ràng.

Theo mặc định xóa **toàn bộ** phần liên quan catalog / import:
  Order(+Item) → Notification → MedicineBatch → ProductVariantUnit →
  ProductVariantStats → ProductVariant → Product → Category → SearchKeyword →
  Voucher → Brand.

Tuỳ chọn `--scope=store-full` còn xóa ShippingMethod, PaymentMethod (sau Order).

Hoặc `--use-flush`: gọi Django `flush` trên DB `store` (rỗng mọi bảng store, tương đương full wipe).

Chạy:
  python manage.py store_reset_catalog --no-input
  python manage.py store_reset_catalog --no-input --scope=catalog
  python manage.py store_reset_catalog --no-input --scope=store-full
  python manage.py store_reset_catalog --no-input --import-csv
  python manage.py store_reset_catalog --no-input --use-flush --import-csv

Không đụng database `default` (mainApp).
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from storeApp.models import (
    Brand,
    Category,
    MedicineBatch,
    Notification,
    Order,
    OrderItem,
    PaymentMethod,
    Product,
    ProductVariant,
    ProductVariantStats,
    ProductVariantUnit,
    SearchKeyword,
    ShippingMethod,
    Voucher,
)


def _delete_qs(stdout, label, qs):
    n, _ = qs.delete()
    stdout.write(f"  · {label}: đã xóa {n} object (gồm CASCADE nếu có).")


def clear_store_import_data(stdout, scope="catalog"):
    """
    scope:
      - catalog: giữ ShippingMethod + PaymentMethod
      - store-full: xóa thêm ShippingMethod, PaymentMethod (chỉ sau khi không còn Order)
    """
    using = "store"

    # Phụ thuộc variant / batch / order — xóa trước
    _delete_qs(stdout, "Notification", Notification.objects.using(using).all())
    _delete_qs(stdout, "OrderItem", OrderItem.objects.using(using).all())
    _delete_qs(stdout, "Order", Order.objects.using(using).all())
    _delete_qs(stdout, "MedicineBatch", MedicineBatch.objects.using(using).all())

    # Đơn vị bán + thống kê + biến thể + sản phẩm
    _delete_qs(
        stdout,
        "ProductVariantUnit",
        ProductVariantUnit.objects.using(using).all(),
    )
    _delete_qs(
        stdout,
        "ProductVariantStats",
        ProductVariantStats.objects.using(using).all(),
    )
    _delete_qs(
        stdout,
        "ProductVariant",
        ProductVariant.objects.using(using).all(),
    )
    _delete_qs(stdout, "Product", Product.objects.using(using).all())

    # Danh mục (cây): sau Product để tránh chỉ SET_NULL; delete() xử lý CASCADE con
    _delete_qs(stdout, "Category", Category.objects.using(using).all())

    _delete_qs(stdout, "SearchKeyword", SearchKeyword.objects.using(using).all())
    _delete_qs(stdout, "Voucher", Voucher.objects.using(using).all())
    _delete_qs(stdout, "Brand", Brand.objects.using(using).all())

    if scope == "store-full":
        _delete_qs(
            stdout,
            "ShippingMethod",
            ShippingMethod.objects.using(using).all(),
        )
        _delete_qs(
            stdout,
            "PaymentMethod",
            PaymentMethod.objects.using(using).all(),
        )


class Command(BaseCommand):
    help = (
        "Xóa dữ liệu catalog/import trên DB store (có thứ tự) hoặc flush toàn DB store; "
        "tuỳ chọn chạy store_catalog import-csv sau."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Không hỏi xác nhận (bắt buộc cho CI/script).",
        )
        parser.add_argument(
            "--skip-clear",
            "--skip-flush",
            action="store_true",
            help="Bỏ bước xóa dữ liệu (chỉ chạy import nếu bật --import-csv). --skip-flush = alias cũ.",
        )
        parser.add_argument(
            "--use-flush",
            action="store_true",
            help="Dùng manage.py flush --database=store thay vì xóa có thứ tự (rỗng toàn bộ bảng store).",
        )
        parser.add_argument(
            "--scope",
            choices=("catalog", "store-full"),
            default="catalog",
            help=(
                "catalog: xóa Order, batch, product tree, category, brand, voucher, keyword… "
                "giữ ShippingMethod/PaymentMethod. "
                "store-full: thêm xóa ShippingMethod và PaymentMethod."
            ),
        )
        parser.add_argument(
            "--import-csv",
            action="store_true",
            help="Sau khi clear, gọi store_catalog import-csv với thư mục --import-path.",
        )
        parser.add_argument(
            "--import-path",
            default="storeApp/test/data/new/",
            help="Tham số path cho store_catalog import-csv (default: storeApp/test/data/new/).",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Truyền --update-existing cho store_catalog import-csv.",
        )
        parser.add_argument(
            "--no-batches",
            action="store_true",
            help="Truyền --no-batches cho store_catalog import-csv.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Dry-run import (không ghi DB) — chỉ hợp lệ cùng --import-csv.",
        )

    def handle(self, *args, **options):
        if not options["no_input"] and not options["skip_clear"]:
            confirm = input(
                "Bạn sắp XÓA dữ liệu catalog/store trên database 'store'. Gõ YES để tiếp tục: "
            )
            if confirm.strip() != "YES":
                self.stdout.write(self.style.ERROR("Đã hủy."))
                return

        if not options["skip_clear"]:
            if options["use_flush"]:
                self.stdout.write(
                    self.style.WARNING("Đang flush toàn bộ database 'store'...")
                )
                call_command(
                    "flush",
                    database="store",
                    interactive=False,
                    verbosity=1,
                )
                self.stdout.write(self.style.SUCCESS("Đã flush xong DB store."))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Đang xóa dữ liệu import/catalog (scope={options['scope']})..."
                    )
                )
                clear_store_import_data(self.stdout, scope=options["scope"])
                self.stdout.write(
                    self.style.SUCCESS("Đã clear dữ liệu catalog/import trên store.")
                )

        if options["import_csv"]:
            self.stdout.write("Chạy store_catalog import-csv...")
            from storeApp.management.commands.catalog_import.run import run_import_csv

            run_import_csv(
                options["import_path"],
                update_existing=options["update_existing"],
                no_batches=options["no_batches"],
                dry_run=options["dry_run"],
            )
            self.stdout.write(self.style.SUCCESS("store_catalog import-csv hoàn tất."))
