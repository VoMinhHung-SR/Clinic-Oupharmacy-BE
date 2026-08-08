"""Public Campaign read API (P2-T1). AllowAny; never leak non-visible campaigns."""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from storeApp.serializers_campaign import (
    PublicCampaignDetailSerializer,
    PublicCampaignListSerializer,
)
from storeApp.services.campaign_cache import (
    get_cached,
    record_public_slug_404,
    set_cached,
)
from storeApp.services.campaign_public import (
    PUBLIC_SLOT_KEYS,
    get_public_campaign_by_slug,
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

    def retrieve(self, request, slug=None):
        cached = get_cached("detail", extra=slug)
        if cached is not None:
            return Response(cached)
        campaign = get_public_campaign_by_slug(slug=slug)
        if campaign is None:
            # Identical 404 for missing / draft / out-of-window (D-06).
            record_public_slug_404(slug or "")
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = PublicCampaignDetailSerializer(campaign).data
        set_cached("detail", data, extra=slug)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="placements")
    def placements(self, request):
        raw = (request.query_params.get("slots") or "").strip()
        slots = None
        if raw:
            slots = [part.strip() for part in raw.split(",") if part.strip()]
            unknown = [s for s in slots if s not in PUBLIC_SLOT_KEYS]
            if unknown:
                return Response(
                    {"detail": f"Unknown slots: {', '.join(unknown)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        extra = tuple(slots) if slots else None
        winners = get_cached("placements", extra=extra)
        if winners is None:
            winners = select_placement_winners(slots=slots)
            set_cached("placements", winners, extra=extra)
        return Response(
            {
                "generated_at": timezone.now().isoformat().replace("+00:00", "Z"),
                "placements": winners,
            }
        )
