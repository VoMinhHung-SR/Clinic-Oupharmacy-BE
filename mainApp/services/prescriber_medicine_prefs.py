"""
Aggregate per-doctor prescribing history for medicine picker quick-access.
No schema changes — reads PrescriptionDetail + hydrates variants from Store App.
"""
from __future__ import annotations

from django.conf import settings

from mainApp.models import PrescriptionDetail
from storeApp.models import ProductCategory, ProductVariant, ProductVariantUnit
from storeApp.serializers import ProductVariantSerializer
from storeApp.viewsets.product import annotate_variant_unit_price

STORE_DB_ALIAS = "store" if "store" in settings.DATABASES else "default"
LOOKBACK_LINES = 500
FREQUENT_LIMIT = 12
RECENT_LIMIT = 12


def _base_detail_qs(user_id: int):
    return PrescriptionDetail.objects.filter(
        active=True,
        product_variant_id__isnull=False,
        prescribing__active=True,
        prescribing__user_id=user_id,
    )


def _aggregate_history(user_id: int):
    """Single pass over recent lines — counts, latest row per variant, recency order."""
    lines = list(
        _base_detail_qs(user_id)
        .select_related("prescribing")
        .order_by("-created_date")[:LOOKBACK_LINES]
    )

    counts: dict[int, int] = {}
    latest: dict[int, PrescriptionDetail] = {}
    recent_order: list[int] = []

    for line in lines:
        vid = line.product_variant_id
        if vid is None:
            continue
        counts[vid] = counts.get(vid, 0) + 1
        if vid not in latest:
            latest[vid] = line
            recent_order.append(vid)

    frequent_ids = sorted(counts.keys(), key=lambda v: counts[v], reverse=True)[:FREQUENT_LIMIT]
    recent_ids = recent_order[:RECENT_LIMIT]
    all_ids = list(dict.fromkeys(frequent_ids + recent_ids))
    return counts, latest, frequent_ids, recent_ids, all_ids


def _hydrate_variants(variant_ids: list[int], *, in_stock_only: bool = False) -> dict[int, dict]:
    if not variant_ids:
        return {}

    from django.db.models import Prefetch

    base_filter = {"id__in": variant_ids, "active": True, "is_published": True}
    qs = ProductVariant.objects.using(STORE_DB_ALIAS).filter(**base_filter)
    if in_stock_only:
        qs = qs.filter(in_stock__gt=0)

    qs = annotate_variant_unit_price(
        qs
        .select_related("product__category", "product__brand")
        .prefetch_related(
            Prefetch(
                "product__product_categories",
                queryset=ProductCategory.objects.using(STORE_DB_ALIAS).select_related("category"),
            ),
            Prefetch(
                "units",
                queryset=ProductVariantUnit.objects.using(STORE_DB_ALIAS)
                .filter(is_published=True)
                .order_by("unit_order", "id"),
                to_attr="prefetched_units",
            ),
        ),
        db_alias=STORE_DB_ALIAS,
    )
    serialized = ProductVariantSerializer(qs, many=True).data
    return {item["id"]: item for item in serialized}


def _build_entry(
    variant_id: int,
    detail: PrescriptionDetail,
    counts: dict[int, int],
    variant_map: dict[int, dict],
):
    variant = variant_map.get(variant_id)
    if not variant:
        return None
    return {
        "product_variant_id": variant_id,
        "product_variant_unit_id": detail.product_variant_unit_id,
        "uses": detail.uses,
        "quantity": detail.quantity,
        "prescribe_count": counts.get(variant_id, 0),
        "last_prescribed_at": detail.created_date.isoformat() if detail.created_date else None,
        "variant": variant,
    }


def get_prescriber_medicine_prefs(user_id: int) -> dict:
    if not user_id:
        return {"frequent": [], "recent": []}

    counts, latest, frequent_ids, recent_ids, all_ids = _aggregate_history(user_id)
    variant_map = _hydrate_variants(all_ids)

    frequent = []
    for vid in frequent_ids:
        entry = _build_entry(vid, latest[vid], counts, variant_map)
        if entry:
            frequent.append(entry)

    recent = []
    for vid in recent_ids:
        entry = _build_entry(vid, latest[vid], counts, variant_map)
        if entry:
            recent.append(entry)

    return {"frequent": frequent, "recent": recent}
