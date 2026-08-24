"""
Upsert homepage CMS demo campaign + placements (P9 content pack).

Images are first-party paths under the storefront `public/mocks/home-cms/`.
Relative URLs resolve on the Next store origin.

Usage:
  python manage.py seed_home_cms_demo
  python manage.py seed_home_cms_demo --database=store --dry-run
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from storeApp.constants import STORE_DATABASE_ALIAS
from storeApp.models import Campaign, CampaignPlacement, CampaignVoucher, Voucher
from storeApp.services.campaign_cache import invalidate_public_campaign_cache

SLUG = "home-cms-p9-demo"
IMG = "/mocks/home-cms"

# Percent tiers for homepage hot-sale rail (must exist via store_import_vouchers).
HOT_SALE_VOUCHER_CODES = ("SALE20", "SALE25", "SALE30")

# (slot, sort_order, title, subtitle, cta_label, cta_url, image_file, image_alt)
PLACEMENTS = [
    (
        CampaignPlacement.SLOT_HOME_HERO,
        0,
        "Tủ thuốc thông minh — Quản lý hạn dùng gia đình",
        "Nhập danh sách thuốc dễ dàng, nhận cảnh báo hết hạn tự động trước 30 ngày.",
        "Trải nghiệm ngay",
        "/tu-thuoc-thong-minh",
        "hero-main-1.png",
        "Tủ thuốc thông minh OUPharmacy",
    ),
    (
        CampaignPlacement.SLOT_HOME_HERO,
        1,
        "Da xinh đón mùa mới — Combo Sạch & Dưỡng chuẩn Y khoa",
        "Giải pháp toàn diện từ sữa rửa mặt thảo dược đến kem chống nắng bảo vệ tối ưu.",
        "Khám phá combo",
        "/khuyen-mai/da-xinh-mua-moi",
        "hero-main-2.png",
        "Combo chăm sóc da mùa mới",
    ),
    (
        CampaignPlacement.SLOT_HOME_SECONDARY,
        0,
        "Tư vấn trực tuyến cùng Dược sĩ chuyên sâu 24/7",
        "Giải đáp mọi thắc mắc về liều dùng, triệu chứng bệnh và đơn thuốc an toàn.",
        "Kết nối ngay",
        "/tu-van-duoc-si",
        "secondary-1.png",
        "Tư vấn dược sĩ trực tuyến",
    ),
    (
        CampaignPlacement.SLOT_HOME_SECONDARY,
        1,
        "Sữa dinh dưỡng cao cấp & Vitamin thiết yếu",
        "Tăng cường sức đề kháng, bảo vệ thể chất toàn diện mỗi ngày. Giảm đến 30% khi mua kèm đơn hàng đầu tiên.",
        "Mua ngay",
        "/tim-kiem?q=vitamin",
        "secondary-2.png",
        "Sữa dinh dưỡng và vitamin",
    ),
    (
        CampaignPlacement.SLOT_HOME_SECONDARY,
        2,
        "Đặc quyền thành viên OUPharmacy",
        "Miễn phí vận chuyển toàn quốc cho đơn hàng từ 300K kèm tích điểm đổi quà. Nhập mã FREESHIP30K.",
        "Lấy mã ngay",
        "/khuyen-mai/dac-quyen-thanh-vien",
        "secondary-3.png",
        "Đặc quyền thành viên FREESHIP30K",
    ),
    (
        CampaignPlacement.SLOT_HOME_NOTICE_TOP,
        0,
        "Hiểu đúng về dược phẩm & Sức khỏe A-Z",
        "Cẩm nang tra cứu triệu chứng, cách sử dụng thuốc an toàn và khoa học cho cả gia đình.",
        "Đọc ngay →",
        "/goc-suc-khoe",
        "notice-top.png",
        "Góc sức khỏe A-Z",
    ),
    (
        CampaignPlacement.SLOT_HOME_NOTICE_BOTTOM,
        0,
        "Tra cứu lịch hẹn khám & Cơ sở nhà thuốc",
        "Hệ thống mạng lưới chi nhánh và lịch trực của đội ngũ bác sĩ, dược sĩ gần bạn nhất.",
        "Tra cứu ngay →",
        "/tim-nha-thuoc",
        "notice-bottom.png",
        "Lịch hẹn và nhà thuốc",
    ),
]


class Command(BaseCommand):
    help = "Upsert home-cms-p9-demo campaign + home placements for local/container QA."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=STORE_DATABASE_ALIAS,
            help=f"Django DB alias (default: {STORE_DATABASE_ALIAS})",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--priority",
            type=int,
            default=200,
            help="Campaign priority (default 200 so it wins home slots).",
        )

    def handle(self, *args, **options):
        db = options["database"]
        dry_run = options["dry_run"]
        priority = options["priority"]
        now = timezone.now()
        start = now - timedelta(days=1)
        end = now + timedelta(days=90)

        campaign = Campaign.objects.using(db).filter(slug=SLUG).first()
        # Only this pack should win home slots — pause every other active campaign.
        others = (
            Campaign.objects.using(db)
            .exclude(slug=SLUG)
            .filter(status=Campaign.STATUS_ACTIVE)
        )
        for other in others:
            self.stdout.write(f"~ pause other campaign {other.slug} id={other.id}")
            if not dry_run:
                other.status = Campaign.STATUS_PAUSED
                other.save(using=db, update_fields=["status"])

        if campaign is None:
            self.stdout.write(f"+ campaign {SLUG}")
            if not dry_run:
                campaign = Campaign.objects.using(db).create(
                    name="Homepage CMS P9 demo",
                    slug=SLUG,
                    title="OUPharmacy — Homepage content pack",
                    subtitle="Hero 2 + Secondary 3 + Notices 2",
                    status=Campaign.STATUS_ACTIVE,
                    priority=priority,
                    start_at=start,
                    end_at=end,
                    locale="vi",
                )
        else:
            self.stdout.write(f"= update campaign {SLUG} id={campaign.id}")
            if not dry_run:
                campaign.name = "Homepage CMS P9 demo"
                campaign.title = "OUPharmacy — Homepage content pack"
                campaign.subtitle = "Hero 2 + Secondary 3 + Notices 2"
                campaign.status = Campaign.STATUS_ACTIVE
                campaign.priority = priority
                campaign.start_at = start
                campaign.end_at = end
                campaign.locale = "vi"
                campaign.save(using=db)

        if dry_run:
            self.stdout.write(f"dry-run: would replace {len(PLACEMENTS)} placements")
            return

        deleted, _ = CampaignPlacement.objects.using(db).filter(campaign=campaign).delete()
        self.stdout.write(f"- cleared {deleted} old placement row(s)")

        for slot, sort_order, title, subtitle, cta_label, cta_url, image_file, image_alt in PLACEMENTS:
            src = f"{IMG}/{image_file}"
            CampaignPlacement.objects.using(db).create(
                campaign=campaign,
                slot=slot,
                title=title,
                subtitle=subtitle,
                cta_label=cta_label,
                cta_url=cta_url,
                image_desktop_url=src,
                image_mobile_url=src,
                image_alt=image_alt,
                sort_order=sort_order,
                is_enabled=True,
            )
            self.stdout.write(f"+ {slot}#{sort_order} → {cta_url}")

        # Hot-sale voucher strip: SALE20 / SALE25 / SALE30 on this home campaign
        for sort_order, code in enumerate(HOT_SALE_VOUCHER_CODES):
            voucher = Voucher.objects.using(db).filter(code=code).first()
            if voucher is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"! missing voucher {code} — run: python manage.py store_import_vouchers"
                    )
                )
                continue
            link, created = CampaignVoucher.objects.using(db).update_or_create(
                campaign=campaign,
                voucher=voucher,
                defaults={"sort_order": sort_order, "is_featured": True},
            )
            mark = "+" if created else "="
            self.stdout.write(f"{mark} campaign voucher {code} sort={sort_order}")

        invalidate_public_campaign_cache()
        self.stdout.write(self.style.SUCCESS(f"seed_home_cms_demo done: {SLUG} id={campaign.id}"))
