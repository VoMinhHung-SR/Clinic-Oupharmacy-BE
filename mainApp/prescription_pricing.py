"""
Single place to resolve unit price for PrescriptionDetail (API + billing).
Order: published ProductVariantUnit for line -> unit_price_snapshot -> default published unit on variant -> 0.
"""
from storeApp.models import ProductVariant, ProductVariantUnit


def resolve_prescription_detail_unit_price(detail):
    """
    Returns (price_float, source) where source is
    'pvu' | 'snapshot' | 'fallback_default_pvu' | 'zero'.
    """
    unit_id = getattr(detail, "product_variant_unit_id", None)
    if unit_id:
        pvu = (
            ProductVariantUnit.objects.using("store")
            .filter(id=unit_id, is_published=True)
            .first()
        )
        if pvu is not None and pvu.price_value is not None:
            return float(pvu.price_value), "pvu"

    snap = getattr(detail, "unit_price_snapshot", None)
    if snap is not None:
        return float(snap), "snapshot"

    variant_id = getattr(detail, "product_variant_id", None)
    if variant_id:
        variant = (
            ProductVariant.objects.using("store")
            .filter(id=variant_id, active=True)
            .first()
        )
        if variant:
            pvu = (
                ProductVariantUnit.objects.using("store")
                .filter(variant_id=variant.id, is_default=True, is_published=True)
                .first()
                or ProductVariantUnit.objects.using("store")
                .filter(variant_id=variant.id, is_published=True)
                .order_by("unit_order", "id")
                .first()
            )
            if pvu is not None and pvu.price_value is not None:
                return float(pvu.price_value), "fallback_default_pvu"

    return 0.0, "zero"
