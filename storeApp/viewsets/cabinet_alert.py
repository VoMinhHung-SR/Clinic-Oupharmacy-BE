from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from storeApp.models import CabinetAlert
from storeApp.serializers_cabinet_alert import CabinetAlertSerializer


class CabinetAlertViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CabinetAlertSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = CabinetAlert.objects.filter(user_id=self.request.user.id, active=True).order_by(
            "-created_date", "-id"
        )
        unread = self.request.query_params.get("unread")
        if unread in ("1", "true", "True"):
            qs = qs.filter(is_read=False)
        return qs

    def get_object(self):
        obj = get_object_or_404(CabinetAlert.objects.all(), pk=self.kwargs["pk"])
        if obj.user_id != self.request.user.id:
            raise PermissionDenied()
        return obj

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        alert = self.get_object()
        alert.mark_as_read()
        return Response(CabinetAlertSerializer(alert).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        from django.utils import timezone

        updated = (
            self.get_queryset()
            .filter(is_read=False)
            .update(is_read=True, read_at=timezone.now())
        )
        return Response({"updated": updated}, status=status.HTTP_200_OK)
