"""Public campaign visibility + placement winner selection (P2-T1)."""

from django.db.models import Prefetch
from django.utils import timezone

from storeApp.models import Campaign, CampaignPlacement, CampaignVoucher

PUBLIC_SLOT_KEYS = [choice[0] for choice in CampaignPlacement.SLOT_CHOICES]


def public_visible_queryset(*, now=None, using="store"):
    """Active campaigns whose window contains now (start_at <= now < end_at)."""
    now = now or timezone.now()
    return (
        Campaign.objects.using(using)
        .filter(
            status=Campaign.STATUS_ACTIVE,
            start_at__isnull=False,
            end_at__isnull=False,
            start_at__lte=now,
            end_at__gt=now,
        )
        .prefetch_related(
            Prefetch(
                "placements",
                queryset=CampaignPlacement.objects.using(using)
                .filter(is_enabled=True)
                .order_by("sort_order", "id"),
            ),
            "products",
            "categories",
            Prefetch(
                "voucher_links",
                queryset=CampaignVoucher.objects.using(using)
                .select_related("voucher")
                .order_by("sort_order", "id"),
            ),
        )
    )


def get_public_campaign_by_slug(*, slug, now=None, using="store"):
    """Return campaign if publicly visible; else None (caller maps to identical 404)."""
    return public_visible_queryset(now=now, using=using).filter(slug=slug).first()


def _placement_rank_key(campaign, placement):
    # Winner: higher priority → earlier start_at → lower campaign id (D-03 / EC-01).
    start_at = campaign.start_at
    return (-campaign.priority, start_at, campaign.id, placement.sort_order, placement.id)


def select_placement_winners(*, now=None, slots=None, using="store"):
    """
    Return dict slot -> winning placement payload or None.
    If slots is None, include every known slot key.
    """
    now = now or timezone.now()
    slot_list = list(slots) if slots else list(PUBLIC_SLOT_KEYS)
    slot_set = set(slot_list)

    candidates = {slot: [] for slot in slot_list}
    campaigns = public_visible_queryset(now=now, using=using)
    for campaign in campaigns:
        for placement in campaign.placements.all():
            if placement.slot not in slot_set:
                continue
            candidates[placement.slot].append((campaign, placement))

    winners = {}
    for slot in slot_list:
        rows = candidates.get(slot) or []
        if not rows:
            winners[slot] = None
            continue
        campaign, placement = min(rows, key=lambda pair: _placement_rank_key(pair[0], pair[1]))
        winners[slot] = {
            "campaign_id": campaign.id,
            "campaign_slug": campaign.slug,
            "title": placement.title,
            "subtitle": placement.subtitle,
            "cta_label": placement.cta_label,
            "cta_url": placement.cta_url,
            "image_desktop_url": placement.image_desktop_url,
            "image_mobile_url": placement.image_mobile_url,
            "image_alt": placement.image_alt,
        }
    return winners


def pick_primary_placement(campaign):
    """Prefer HOME_HERO enabled placement; else first by sort_order."""
    placements = list(campaign.placements.all())
    if not placements:
        return None
    for placement in placements:
        if placement.slot == CampaignPlacement.SLOT_HOME_HERO:
            return placement
    return placements[0]


def is_voucher_displayable(voucher):
    """Merchandising display: reuse Voucher.is_valid() — no new discount math (D-07 / SC-05)."""
    if voucher is None:
        return False
    return bool(voucher.is_valid())


def public_voucher_payloads(campaign):
    """Omit non-displayable vouchers entirely (D-07)."""
    links = list(getattr(campaign, "voucher_links").all()) if hasattr(campaign, "voucher_links") else []
    payloads = []
    for link in links:
        voucher = getattr(link, "voucher", None)
        if not is_voucher_displayable(voucher):
            continue
        payloads.append(
            {
                "code": voucher.code,
                "description": voucher.description,
                "type": voucher.type,
                "value": str(voucher.value),
                "scope": voucher.scope,
                "is_displayable": True,
                "is_featured": bool(link.is_featured),
            }
        )
    return payloads
