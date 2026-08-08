"""Admin REST for Campaign CRUD + lifecycle + placements replace (P1-T3)."""

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from storeApp.models import Campaign, CampaignCategory, CampaignPlacement, CampaignProduct, CampaignVoucher
from storeApp.permissions.campaign_permissions import CanManageCampaign, CanViewCampaign
from storeApp.serializers_campaign import (
    CampaignActionSerializer,
    CampaignCategoriesReplaceSerializer,
    CampaignPlacementsReplaceSerializer,
    CampaignProductsReplaceSerializer,
    CampaignSerializer,
    CampaignVouchersReplaceSerializer,
    CampaignWriteSerializer,
)
from storeApp.services.campaign_cache import invalidate_public_campaign_cache
from storeApp.services.campaign_service import (
    CampaignServiceError,
    CampaignTransitionError,
    CampaignVersionConflictError,
    archive_campaign,
    end_campaign,
    pause_campaign,
    publish_campaign,
    resume_campaign,
    schedule_campaign,
)


def _actor_id(request):
    user = getattr(request, "user", None)
    return getattr(user, "id", None) if user and user.is_authenticated else None


def _error_response(exc):
    if isinstance(exc, CampaignVersionConflictError):
        return Response(
            {
                "code": "version_conflict",
                "detail": str(exc),
                "expected_version": exc.expected_version,
                "current_version": exc.current_version,
            },
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, CampaignTransitionError):
        return Response(
            {
                "code": "illegal_transition",
                "detail": str(exc),
                "from_status": exc.from_status,
                "to_status": exc.to_status,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, CampaignServiceError):
        return Response({"code": "campaign_error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    raise exc


def _campaign_qs():
    return Campaign.objects.prefetch_related(
        "placements", "products", "categories", "voucher_links"
    ).annotate(attributed_order_count=Count("orders", distinct=True))


class CampaignAdminViewSet(viewsets.ViewSet):
    """
    /api/store/admin/campaigns/
    Numeric id only (public slug routes land in a later phase).
    """

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [CanViewCampaign()]
        return [CanManageCampaign()]

    def list(self, request):
        qs = _campaign_qs().order_by("-priority", "start_at", "id")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(CampaignSerializer(qs, many=True).data)

    def create(self, request):
        ser = CampaignWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = {k: v for k, v in ser.validated_data.items() if k != "version"}
        campaign = Campaign.objects.create(
            **data,
            status=Campaign.STATUS_DRAFT,
            created_by_id=_actor_id(request),
            updated_by_id=_actor_id(request),
        )
        campaign = _campaign_qs().get(
            id=campaign.id
        )
        return Response(CampaignSerializer(campaign).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        campaign = get_object_or_404(
            _campaign_qs(),
            pk=pk,
        )
        return Response(CampaignSerializer(campaign).data)

    def partial_update(self, request, pk=None):
        campaign = get_object_or_404(Campaign, pk=pk)
        ser = CampaignWriteSerializer(campaign, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        expected = ser.validated_data.get("version")
        if expected is None:
            return Response(
                {"code": "version_required", "detail": "version is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if campaign.version != expected:
            return Response(
                {
                    "code": "version_conflict",
                    "detail": "stale version",
                    "expected_version": expected,
                    "current_version": campaign.version,
                },
                status=status.HTTP_409_CONFLICT,
            )
        if campaign.status == Campaign.STATUS_ARCHIVED:
            return Response(
                {"code": "campaign_error", "detail": "archived campaigns are not editable"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic(using="store"):
            locked = Campaign.objects.select_for_update().get(id=campaign.id)
            if locked.version != expected:
                return Response(
                    {
                        "code": "version_conflict",
                        "detail": "stale version",
                        "expected_version": expected,
                        "current_version": locked.version,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            for field, value in ser.validated_data.items():
                if field == "version":
                    continue
                setattr(locked, field, value)
            locked.updated_by_id = _actor_id(request)
            from django.db.models import F

            locked.version = F("version") + 1
            update_fields = [f for f in ser.validated_data.keys() if f != "version"] + [
                "updated_by_id",
                "version",
                "updated_date",
            ]
            locked.save(update_fields=update_fields)
            locked.refresh_from_db()

        locked = _campaign_qs().get(
            id=locked.id
        )
        invalidate_public_campaign_cache()
        return Response(CampaignSerializer(locked).data)

    def _run_action(self, request, pk, service_fn):
        ser = CampaignActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            campaign = service_fn(
                campaign_id=int(pk),
                expected_version=ser.validated_data["version"],
                actor_user_id=_actor_id(request),
            )
        except (CampaignServiceError, CampaignVersionConflictError, CampaignTransitionError) as exc:
            return _error_response(exc)
        campaign = _campaign_qs().get(
            id=campaign.id
        )
        return Response(CampaignSerializer(campaign).data)

    @action(detail=True, methods=["post"], url_path="schedule")
    def schedule(self, request, pk=None):
        return self._run_action(request, pk, schedule_campaign)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        return self._run_action(request, pk, publish_campaign)

    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        return self._run_action(request, pk, pause_campaign)

    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        return self._run_action(request, pk, resume_campaign)

    @action(detail=True, methods=["post"], url_path="end")
    def end(self, request, pk=None):
        return self._run_action(request, pk, end_campaign)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        return self._run_action(request, pk, archive_campaign)

    @action(detail=True, methods=["put"], url_path="placements")
    def replace_placements(self, request, pk=None):
        ser = CampaignPlacementsReplaceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        expected = ser.validated_data["version"]
        placements_data = ser.validated_data["placements"]

        try:
            with transaction.atomic(using="store"):
                campaign = Campaign.objects.select_for_update().get(id=pk)
                if campaign.version != expected:
                    raise CampaignVersionConflictError(
                        expected_version=expected,
                        current_version=campaign.version,
                    )
                if campaign.status == Campaign.STATUS_ARCHIVED:
                    raise CampaignServiceError("archived campaigns are not editable")

                CampaignPlacement.objects.filter(campaign_id=campaign.id).delete()
                for row in placements_data:
                    CampaignPlacement.objects.create(campaign=campaign, **row)

                from django.db.models import F

                campaign.updated_by_id = _actor_id(request)
                campaign.version = F("version") + 1
                campaign.save(update_fields=["updated_by_id", "version", "updated_date"])
                campaign.refresh_from_db()
        except Campaign.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except (CampaignServiceError, CampaignVersionConflictError) as exc:
            return _error_response(exc)

        campaign = _campaign_qs().get(
            id=campaign.id
        )
        invalidate_public_campaign_cache()
        return Response(CampaignSerializer(campaign).data)

    def _replace_scope(self, request, pk, *, ser_cls, apply_rows):
        ser = ser_cls(data=request.data)
        ser.is_valid(raise_exception=True)
        expected = ser.validated_data["version"]

        try:
            with transaction.atomic(using="store"):
                campaign = Campaign.objects.select_for_update().get(id=pk)
                if campaign.version != expected:
                    raise CampaignVersionConflictError(
                        expected_version=expected,
                        current_version=campaign.version,
                    )
                if campaign.status == Campaign.STATUS_ARCHIVED:
                    raise CampaignServiceError("archived campaigns are not editable")

                apply_rows(campaign, ser.validated_data)

                from django.db.models import F

                campaign.updated_by_id = _actor_id(request)
                campaign.version = F("version") + 1
                campaign.save(update_fields=["updated_by_id", "version", "updated_date"])
                campaign.refresh_from_db()
        except Campaign.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except (CampaignServiceError, CampaignVersionConflictError) as exc:
            return _error_response(exc)

        campaign = _campaign_qs().get(
            id=campaign.id
        )
        invalidate_public_campaign_cache()
        return Response(CampaignSerializer(campaign).data)

    @action(detail=True, methods=["put"], url_path="products")
    def replace_products(self, request, pk=None):
        def apply_rows(campaign, data):
            CampaignProduct.objects.filter(campaign_id=campaign.id).delete()
            for index, mid in enumerate(data["product_mids"]):
                CampaignProduct.objects.create(
                    campaign=campaign,
                    product_mid=mid,
                    sort_order=index,
                )

        return self._replace_scope(
            request,
            pk,
            ser_cls=CampaignProductsReplaceSerializer,
            apply_rows=apply_rows,
        )

    @action(detail=True, methods=["put"], url_path="categories")
    def replace_categories(self, request, pk=None):
        def apply_rows(campaign, data):
            CampaignCategory.objects.filter(campaign_id=campaign.id).delete()
            for index, slug in enumerate(data["category_slugs"]):
                CampaignCategory.objects.create(
                    campaign=campaign,
                    category_slug=slug,
                    sort_order=index,
                )

        return self._replace_scope(
            request,
            pk,
            ser_cls=CampaignCategoriesReplaceSerializer,
            apply_rows=apply_rows,
        )

    @action(detail=True, methods=["put"], url_path="vouchers")
    def replace_vouchers(self, request, pk=None):
        def apply_rows(campaign, data):
            CampaignVoucher.objects.filter(campaign_id=campaign.id).delete()
            for index, row in enumerate(data["vouchers"]):
                CampaignVoucher.objects.create(
                    campaign=campaign,
                    voucher_id=row["voucher_id"],
                    sort_order=row.get("sort_order", index),
                    is_featured=row.get("is_featured", True),
                )

        return self._replace_scope(
            request,
            pk,
            ser_cls=CampaignVouchersReplaceSerializer,
            apply_rows=apply_rows,
        )
