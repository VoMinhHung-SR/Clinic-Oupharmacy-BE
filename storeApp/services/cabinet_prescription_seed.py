"""List PrescriptionDetail lines for the logged-in patient to seed a cabinet."""

from django.db.models import Q

from mainApp.models import PrescriptionDetail
from storeApp.models import ProductVariant, ProductVariantUnit
from storeApp.serializers_cabinet import variant_image_url

LIST_CAP = 100


def _owner_filter(user_id: int) -> Q:
    return (
        Q(prescribing__diagnosis__patient__user_id=user_id)
        | Q(prescribing__diagnosis__examination__patient__user_id=user_id)
        | Q(prescribing__diagnosis__examination__user_id=user_id)
    )


def _product_name(detail, variant):
    if detail.item_name_snapshot:
        return detail.item_name_snapshot
    if variant is None:
        return None
    try:
        product = variant.product
        return product.web_name or product.name
    except Exception:
        return None


def list_prescription_lines_for_user(user_id: int, *, limit: int = LIST_CAP) -> list:
    """
    Owner-scoped prescription lines from mainApp, hydrated from store catalog when possible.
    Does not invent HSD. Lines without a published variant+unit stay variant_available=false.
    """
    details = list(
        PrescriptionDetail.objects.using("default")
        .filter(active=True, prescribing__active=True, prescribing__diagnosis__active=True)
        .filter(_owner_filter(user_id))
        .select_related("prescribing", "prescribing__diagnosis")
        .order_by("-created_date", "-id")[: max(1, int(limit))]
    )

    variant_ids = {row.product_variant_id for row in details if row.product_variant_id}
    unit_ids = {row.product_variant_unit_id for row in details if row.product_variant_unit_id}

    variants = {
        v.id: v
        for v in ProductVariant.objects.filter(
            id__in=variant_ids, active=True, is_published=True
        ).select_related("product")
    }
    units = {
        u.id: u
        for u in ProductVariantUnit.objects.filter(id__in=unit_ids, is_published=True).select_related(
            "variant__product"
        )
    }

    # Units may point at variants not listed on the detail row — include them for hydrate.
    for unit in units.values():
        if unit.variant_id and unit.variant_id not in variants:
            variant = getattr(unit, "variant", None)
            if (
                variant is not None
                and variant.active
                and variant.is_published
            ):
                variants[variant.id] = variant

    rows = []
    for detail in details:
        variant = variants.get(detail.product_variant_id) if detail.product_variant_id else None
        unit = units.get(detail.product_variant_unit_id) if detail.product_variant_unit_id else None

        if unit and variant and unit.variant_id != variant.id:
            unit = None
        if unit and not variant:
            variant = variants.get(unit.variant_id)

        available = bool(variant and unit)
        diagnosis = getattr(detail.prescribing, "diagnosis", None)

        rows.append(
            {
                "id": detail.id,
                "prescribing_id": detail.prescribing_id,
                "prescribed_at": detail.created_date.isoformat() if detail.created_date else None,
                "diagnosis_label": getattr(diagnosis, "diagnosed", None) if diagnosis else None,
                "quantity": detail.quantity,
                "uses": detail.uses,
                "product_variant_id": variant.id if variant else detail.product_variant_id,
                "product_variant_unit_id": unit.id if unit else detail.product_variant_unit_id,
                "item_name": _product_name(detail, variant),
                "unit_name": (unit.unit_name if unit else None) or detail.unit_name_snapshot,
                "packing": getattr(variant, "packing", None) if variant else None,
                "image_url": variant_image_url(variant) if variant else None,
                "variant_available": available,
            }
        )
    return rows
