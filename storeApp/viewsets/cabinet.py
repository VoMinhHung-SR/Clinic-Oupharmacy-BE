from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from storeApp.models import Cabinet, CabinetItem
from storeApp.models.cabinet import DEFAULT_CABINET_NAME, EXPIRED, EXPIRING, EXPIRING_SOON, LOW_STOCK
from storeApp.serializers_cabinet import (
    CabinetItemSerializer,
    CabinetSerializer,
    apply_expiration_status_filter,
)

OVERVIEW_LIST_CAP = 10


class CabinetViewSet(viewsets.ModelViewSet):
    serializer_class = CabinetSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Cabinet.objects.filter(user_id=self.request.user.id).order_by("id")

    def get_object(self):
        obj = get_object_or_404(Cabinet.objects.all(), pk=self.kwargs["pk"])
        if obj.user_id != self.request.user.id:
            raise PermissionDenied()
        return obj

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        if not qs.exists():
            Cabinet.objects.create(user_id=request.user.id, name=DEFAULT_CABINET_NAME)
        return super().list(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if self.get_queryset().count() <= 1:
            return Response(
                {"detail": "Không thể xóa tủ thuốc cuối cùng."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def overview(self, request, pk=None):
        cabinet = self.get_object()
        items = list(
            cabinet.items.select_related(
                "cabinet",
                "product_variant__product",
                "product_variant_unit",
            ).order_by("expiration_date", "id")
        )
        serialized = CabinetItemSerializer(items, many=True, context={"request": request}).data
        expired = [row for row in serialized if row["expiration_status"] == EXPIRED]
        soon = [row for row in serialized if row["expiration_status"] == EXPIRING_SOON]
        expiring = [row for row in serialized if row["expiration_status"] == EXPIRING]
        low_stock = [row for row in serialized if row["inventory_status"] == LOW_STOCK]
        refill = [row for row in serialized if row.get("on_refill_list")]
        out_of_stock = sum(1 for row in serialized if row["inventory_status"] == "OUT_OF_STOCK")
        return Response(
            {
                "cabinet": CabinetSerializer(cabinet).data,
                "counts": {
                    "total": len(serialized),
                    "expired": len(expired),
                    "expiring_soon": len(soon),
                    "expiring": len(expiring),
                    "low_stock": len(low_stock),
                    "in_stock": len(serialized) - out_of_stock,
                    "out_of_stock": out_of_stock,
                    "on_refill_list": len(refill),
                },
                "expired": expired[:OVERVIEW_LIST_CAP],
                "expiring_soon": soon[:OVERVIEW_LIST_CAP],
                "low_stock": low_stock[:OVERVIEW_LIST_CAP],
                "refill_list": refill[:OVERVIEW_LIST_CAP],
            }
        )


class CabinetItemViewSet(viewsets.ModelViewSet):
    serializer_class = CabinetItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = CabinetItem.objects.filter(cabinet__user_id=self.request.user.id).select_related(
            "cabinet",
            "product_variant__product",
            "product_variant_unit",
        )
        cabinet_id = self.request.query_params.get("cabinet")
        if cabinet_id:
            qs = qs.filter(cabinet_id=cabinet_id)
        status_filter = self.request.query_params.get("expiration_status")
        if status_filter:
            soon_days = None
            if cabinet_id:
                soon_days = (
                    Cabinet.objects.filter(pk=cabinet_id, user_id=self.request.user.id)
                    .values_list("expiring_soon_days", flat=True)
                    .first()
                )
            qs = apply_expiration_status_filter(qs, status_filter, soon_days=soon_days)
        return qs.order_by("expiration_date", "id")

    def get_object(self):
        obj = get_object_or_404(
            CabinetItem.objects.select_related("cabinet"),
            pk=self.kwargs["pk"],
        )
        if obj.cabinet.user_id != self.request.user.id:
            raise PermissionDenied()
        return obj
