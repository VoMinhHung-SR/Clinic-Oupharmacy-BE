"""Scan cabinet items and create user-scoped HSD alerts (inbox channel)."""

from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from storeApp.models import CabinetAlert, CabinetItem
from storeApp.models.cabinet import (
    ALERT_EXPIRED,
    ALERT_EXPIRING_SOON,
    DEFAULT_ALERT_DEDUPE_DAYS,
    EXPIRED,
    EXPIRING_SOON,
)

# Cap inbox flood when a user imports many medicines at once.
MAX_ALERTS_PER_USER_PER_SCAN = 10


def _product_label(item: CabinetItem) -> str:
    try:
        product = item.product_variant.product
        return (product.web_name or product.name or "").strip() or f"Thuốc #{item.id}"
    except Exception:
        return f"Thuốc #{item.id}"


def _build_copy(kind, item, days):
    name = _product_label(item)
    hsd = item.expiration_date.isoformat() if item.expiration_date else ""
    if kind == ALERT_EXPIRED:
        title = f"Đã hết hạn: {name}"
        body = f"{name} đã hết hạn sử dụng ({hsd}). Kiểm tra tủ thuốc và xử lý an toàn."
        return title, body
    title = f"Sắp hết hạn: {name}"
    days_part = f" còn {days} ngày" if days is not None else ""
    body = f"{name} sắp hết hạn{days_part} (HSD {hsd}). Xem lại tủ thuốc của bạn."
    return title, body


def scan_cabinet_expiry_alerts(*, today=None, dedupe_days: int = DEFAULT_ALERT_DEDUPE_DAYS) -> dict:
    """
    Create EXPIRING_SOON / EXPIRED alerts for cabinets with reminder_enabled.
    Does not touch warehouse Notification / MedicineBatch.

    Anti-spam:
    - Dedupe window covers active *and* inactive alerts (dismissed still block recreate for N days).
    - Any previously dismissed (active=False) item+kind pair is blocked permanently.
    - At most MAX_ALERTS_PER_USER_PER_SCAN new alerts per user per run.
    """
    today = today or timezone.now().date()
    since = timezone.now() - timedelta(days=max(1, int(dedupe_days)))

    items = list(
        CabinetItem.objects.filter(active=True, cabinet__active=True, cabinet__reminder_enabled=True)
        .select_related("cabinet", "product_variant__product")
        .order_by("id")
    )

    item_ids = [item.id for item in items]
    recent_keys = set()
    dismissed_keys = set()
    if item_ids:
        recent_keys = set(
            CabinetAlert.objects.filter(
                cabinet_item_id__in=item_ids,
                kind__in=[ALERT_EXPIRED, ALERT_EXPIRING_SOON],
                created_date__gte=since,
            ).values_list("cabinet_item_id", "kind")
        )
        dismissed_keys = set(
            CabinetAlert.objects.filter(
                cabinet_item_id__in=item_ids,
                kind__in=[ALERT_EXPIRED, ALERT_EXPIRING_SOON],
                active=False,
            ).values_list("cabinet_item_id", "kind")
        )

    created = 0
    skipped_dedupe = 0
    skipped_status = 0
    skipped_dismissed = 0
    skipped_cap = 0
    created_by_user = defaultdict(int)

    for item in items:
        status = item.expiration_status(today=today)
        if status == EXPIRED:
            kind = ALERT_EXPIRED
        elif status == EXPIRING_SOON:
            kind = ALERT_EXPIRING_SOON
        else:
            skipped_status += 1
            continue

        key = (item.id, kind)
        if key in dismissed_keys:
            skipped_dismissed += 1
            continue

        if key in recent_keys:
            skipped_dedupe += 1
            continue

        user_id = item.cabinet.user_id
        if created_by_user[user_id] >= MAX_ALERTS_PER_USER_PER_SCAN:
            skipped_cap += 1
            continue

        title, body = _build_copy(kind, item, item.days_until_expiry(today=today))
        CabinetAlert.objects.create(
            user_id=user_id,
            cabinet_item=item,
            kind=kind,
            title=title,
            body=body,
            is_read=False,
        )
        recent_keys.add(key)
        created_by_user[user_id] += 1
        created += 1

    return {
        "created": created,
        "skipped_dedupe": skipped_dedupe,
        "skipped_status": skipped_status,
        "skipped_dismissed": skipped_dismissed,
        "skipped_cap": skipped_cap,
        "scanned": len(items),
        "dedupe_days": dedupe_days,
        "today": today.isoformat(),
    }
