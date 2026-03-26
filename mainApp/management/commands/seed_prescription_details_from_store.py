"""
Gán lại dữ liệu PrescriptionDetail (dev): random sản phẩm từ store, random quantity & uses.

Không trừ tồn kho — chỉ ghi snapshot + soft-reference store (giống hướng refactor model).
medicine_unit được set NULL.

Sau khi tạo chi tiết đơn, tự tạo/cập nhật Bill theo đơn (tiền thuốc + SERVICE_FEE_PER_PRESCRIBING)
và đặt created_date/updated_date của Bill trùng mốc thời gian với phiếu khám (Examination) nếu có,
không thì theo Prescribing/Diagnosis — khớp logic thanh toán với mainApp.viewsets.bill.

Chạy sau khi store đã có ProductVariant + ProductVariantUnit (vd: store_reset_catalog --import-csv):

  python manage.py seed_prescription_details_from_store --no-input
  python manage.py seed_prescription_details_from_store --no-input --clear-bills
"""

from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from mainApp.constant import SERVICE_FEE_PER_PRESCRIBING
from mainApp.models import Bill, PrescriptionDetail, Prescribing
from mainApp.viewsets.bill import _resolve_unit_price
from storeApp.models import ProductVariant, ProductVariantUnit


USES_POOL = (
    "Sáng 1 lần, tối 1 lần sau ăn",
    "Ngày 2 lần, mỗi lần 1 viên"
)


def _reference_datetime_for_bill(prescribing):
    """
    Ưu tiên ngày/giờ phiếu khám (Examination); sau đó Prescribing, Diagnosis.
    Dùng làm created_date/updated_date cho Bill để cùng ngày với chuỗi khám–kê toa.
    """
    diagnosis = getattr(prescribing, "diagnosis", None)
    if diagnosis:
        ex = getattr(diagnosis, "examination", None)
        if ex and getattr(ex, "created_date", None):
            return ex.created_date
        if getattr(diagnosis, "created_date", None):
            return diagnosis.created_date
    if getattr(prescribing, "created_date", None):
        return prescribing.created_date
    return None


def _medicine_cost_for_prescribing(prescribing):
    total = 0.0
    details = PrescriptionDetail.objects.filter(
        prescribing=prescribing, active=True
    )
    for detail in details:
        total += _resolve_unit_price(detail) * int(detail.quantity)
    return total


def _rebuild_bills_for_prescribings(prescribings, stdout):
    """
    Một Bill / một Prescribing; amount = tiền thuốc + phí dịch vụ (giống bulk_payment đơn lẻ).
    """
    created_or_updated = 0
    for pr in prescribings:
        details = PrescriptionDetail.objects.filter(prescribing=pr, active=True)
        if not details.exists():
            Bill.objects.filter(prescribing=pr).delete()
            continue

        medicine_cost = _medicine_cost_for_prescribing(pr)
        total_amount = float(medicine_cost) + float(SERVICE_FEE_PER_PRESCRIBING)

        bill, _ = Bill.objects.update_or_create(
            prescribing=pr,
            defaults={"amount": total_amount, "active": True},
        )

        ref = _reference_datetime_for_bill(pr)
        if ref is not None:
            Bill.objects.filter(pk=bill.pk).update(
                created_date=ref,
                updated_date=ref,
            )
        created_or_updated += 1

    stdout.write(
        f"Đã tạo/cập nhật Bill cho {created_or_updated} đơn kê (theo chi tiết + phí dịch vụ)."
    )


def _pick_pvu(variant):
    pvu = (
        ProductVariantUnit.objects.using("store")
        .filter(variant_id=variant.id, is_default=True, is_published=True)
        .first()
    )
    if pvu:
        return pvu
    return (
        ProductVariantUnit.objects.using("store")
        .filter(variant_id=variant.id, is_published=True)
        .order_by("unit_order", "id")
        .first()
    )


class Command(BaseCommand):
    help = "Xóa PrescriptionDetail hiện tại và tạo lại ngẫu nhiên từ store (variant + snapshot)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Không hỏi xác nhận.",
        )
        parser.add_argument(
            "--clear-bills",
            action="store_true",
            help="Xóa toàn bộ Bill trước khi seed; cuối lệnh vẫn tạo lại Bill theo đơn + ngày khám.",
        )
        parser.add_argument(
            "--no-rebuild-bills",
            action="store_true",
            help="Không tạo/cập nhật Bill sau khi seed (mặc định: luôn rebuild).",
        )
        parser.add_argument(
            "--min-lines",
            type=int,
            default=1,
            help="Tối thiểu số dòng thuốc mỗi đơn kê (default 1).",
        )
        parser.add_argument(
            "--max-lines",
            type=int,
            default=4,
            help="Tối đa số dòng thuốc mỗi đơn kê (default 4).",
        )
        parser.add_argument(
            "--min-qty",
            type=int,
            default=1,
            help="Quantity tối thiểu mỗi dòng (default 1).",
        )
        parser.add_argument(
            "--max-qty",
            type=int,
            default=10,
            help="Quantity tối đa mỗi dòng (default 10).",
        )

    def handle(self, *args, **options):
        if not options["no_input"]:
            c = input(
                "Sẽ XÓA hết PrescriptionDetail và tạo lại random. Gõ YES: "
            )
            if c.strip() != "YES":
                self.stdout.write(self.style.ERROR("Đã hủy."))
                return

        min_l = max(1, options["min_lines"])
        max_l = max(min_l, options["max_lines"])
        min_q = max(1, options["min_qty"])
        max_q = max(min_q, options["max_qty"])

        variants = list(
            ProductVariant.objects.using("store")
            .filter(active=True, is_published=True)
            .select_related("product")
        )
        if not variants:
            self.stdout.write(
                self.style.ERROR(
                    "Không có ProductVariant nào trên store. Chạy store_reset_catalog --import-csv trước."
                )
            )
            return

        prescribings = list(
            Prescribing.objects.filter(active=True).select_related(
                "diagnosis__examination"
            )
        )
        if not prescribings:
            self.stdout.write(
                self.style.WARNING("Không có Prescribing active — không tạo dòng nào.")
            )
            return

        with transaction.atomic():
            deleted_pd = PrescriptionDetail.objects.all().delete()
            self.stdout.write(f"Đã xóa PrescriptionDetail: {deleted_pd}")

            if options["clear_bills"]:
                deleted_b = Bill.objects.all().delete()
                self.stdout.write(f"Đã xóa Bill: {deleted_b}")

            created = 0
            for pr in prescribings:
                n = random.randint(min_l, max_l)
                for _ in range(n):
                    variant = random.choice(variants)
                    pvu = _pick_pvu(variant)
                    qib = int(pvu.quantity_in_base) if pvu else 1
                    price = (
                        Decimal(str(pvu.price_value))
                        if pvu and pvu.price_value is not None
                        else Decimal("0")
                    )
                    product = variant.product
                    item_name = (product.web_name or product.name or "")[:500]
                    unit_name = ""
                    if pvu:
                        unit_name = (pvu.unit_name or "")[:100]
                    elif variant.packing:
                        unit_name = (variant.packing or "")[:100]

                    PrescriptionDetail.objects.create(
                        prescribing=pr,
                        quantity=random.randint(min_q, max_q),
                        uses=(random.choice(USES_POOL))[:100],
                        product_id=variant.product_id,
                        product_variant_id=variant.id,
                        product_variant_unit_id=pvu.id if pvu else None,
                        item_name_snapshot=item_name or None,
                        unit_name_snapshot=unit_name or None,
                        unit_price_snapshot=price,
                        quantity_in_base_snapshot=qib,
                    )
                    created += 1

            if not options["no_rebuild_bills"]:
                _rebuild_bills_for_prescribings(prescribings, self.stdout)

        self.stdout.write(self.style.SUCCESS(f"Đã tạo {created} PrescriptionDetail."))
