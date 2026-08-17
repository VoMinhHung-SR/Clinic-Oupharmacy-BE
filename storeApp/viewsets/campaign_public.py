"""Public Campaign read API (P2-T1). AllowAny; never leak non-visible campaigns."""

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from storeApp.models import Campaign, CampaignPlacement, CampaignVoucher
from storeApp.serializers_campaign import (
    PublicCampaignDetailSerializer,
    PublicCampaignListSerializer,
)
from storeApp.services.campaign_cache import (
    get_cached,
    record_public_slug_404,
    set_cached,
)
from storeApp.services.campaign_preview import unsign_campaign_preview
from storeApp.services.campaign_public import (
    PUBLIC_SLOT_KEYS,
    get_public_campaign_by_slug,
    normalize_placement_slot,
    public_visible_queryset,
    select_placement_winners,
)


class CampaignPublicViewSet(viewsets.ViewSet):
    """
    GET /api/store/campaigns/
    GET /api/store/campaigns/placements/
    GET /api/store/campaigns/{slug}/
    """

    permission_classes = [AllowAny]
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def list(self, request):
        cached = get_cached("list")
        if cached is not None:
            return Response(cached)
        qs = public_visible_queryset().order_by("-priority", "start_at", "id")
        data = PublicCampaignListSerializer(qs, many=True).data
        set_cached("list", data)
        return Response(data)

    def _not_found(self, slug):
        # Identical 404 for missing / draft / bad preview (D-06 / D-19).
        record_public_slug_404(slug or "")
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def _retrieve_preview(self, *, slug, token):
        """Preview Response, or None to fall through to public retrieve (D-19f)."""
        parsed = unsign_campaign_preview(token)
        if parsed is None:
            return self._not_found(slug)
        pk, signed_slug = parsed
        if signed_slug != slug:
            return self._not_found(slug)

        campaign = (
            Campaign.objects.using("store")
            .filter(pk=pk, slug=slug)
            .prefetch_related(
                Prefetch(
                    "placements",
                    queryset=CampaignPlacement.objects.using("store")
                    .filter(is_enabled=True)
                    .order_by("sort_order", "id"),
                ),
                "products",
                "categories",
                Prefetch(
                    "voucher_links",
                    queryset=CampaignVoucher.objects.using("store")
                    .select_related("voucher")
                    .order_by("sort_order", "id"),
                ),
            )
            .first()
        )
        if campaign is None:
            return self._not_found(slug)

        if get_public_campaign_by_slug(slug=slug) is not None:
            return None

        data = PublicCampaignDetailSerializer(campaign).data
        return Response({**data, "is_preview": True})

    def retrieve(self, request, slug=None):
        raw = request.query_params.get("preview")
        if raw is not None:
            preview_response = self._retrieve_preview(slug=slug, token=raw)
            if preview_response is not None:
                return preview_response

        cached = get_cached("detail", extra=slug)
        if cached is not None:
            return Response(cached)
        campaign = get_public_campaign_by_slug(slug=slug)
        if campaign is None:
            return self._not_found(slug)
        data = PublicCampaignDetailSerializer(campaign).data
        set_cached("detail", data, extra=slug)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="placements")
    def placements(self, request):
        raw = (request.query_params.get("slots") or "").strip()
        slots = None
        if raw:
            slots = [normalize_placement_slot(part.strip()) for part in raw.split(",") if part.strip()]
            # Dedupe after alias normalize while keeping order
            deduped = []
            seen = set()
            for s in slots:
                if s in seen:
                    continue
                seen.add(s)
                deduped.append(s)
            slots = deduped
            unknown = [s for s in slots if s not in PUBLIC_SLOT_KEYS]
            if unknown:
                return Response(
                    {"detail": f"Unknown slots: {', '.join(unknown)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        extra = tuple(slots) if slots else None
        # P9 shape bump — avoid serving pre-D-22 cached objects as arrays.
        winners = get_cached("placements_p9", extra=extra)
        if winners is None:
            winners = select_placement_winners(slots=slots)
            set_cached("placements_p9", winners, extra=extra)
        return Response(
            {
                "generated_at": timezone.now().isoformat().replace("+00:00", "Z"),
                "placements": winners,
            }
        )
