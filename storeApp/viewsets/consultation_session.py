from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mainApp.authz import is_business_admin
from storeApp.models.consultation import ConsultationSession
from storeApp.permissions.consultation_permissions import IsPharmacist, is_pharmacist
from storeApp.serializers_consultation import (
    ConsultationSessionCreateSerializer,
    ConsultationSessionPatchSerializer,
    ConsultationSessionSerializer,
)
from storeApp.services.consultation import pharmacist_queue


class ConsultationSessionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Pharmacist consultation sessions. Messages live in Firestore, not Django."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = None

    def get_permissions(self):
        if self.action == "claim":
            return [IsPharmacist()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == "create":
            return ConsultationSessionCreateSerializer
        if self.action in ("partial_update", "update"):
            return ConsultationSessionPatchSerializer
        return ConsultationSessionSerializer

    def get_queryset(self):
        user = self.request.user
        qs = ConsultationSession.objects.filter(active=True)
        scope = (self.request.query_params.get("scope") or "mine").strip().lower()
        status_filter = (self.request.query_params.get("status") or "").strip()

        if scope == "queue":
            if not is_pharmacist(user):
                raise PermissionDenied("Chỉ dược sĩ mới xem hàng chờ.")
            qs = qs.filter(
                Q(
                    status=ConsultationSession.WAITING_FOR_PROFESSIONAL,
                    pharmacist_id__isnull=True,
                )
                | Q(pharmacist_id=user.id)
            )
        elif is_pharmacist(user) and self.request.query_params.get("as_user") != "1":
            qs = qs.filter(pharmacist_id=user.id)
        else:
            qs = qs.filter(user_id=user.id)

        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by("-created_date", "-id")

    def get_object(self):
        obj = get_object_or_404(ConsultationSession.objects.filter(active=True), pk=self.kwargs["pk"])
        if is_business_admin(self.request.user):
            return obj
        pharmacist_queue.assert_owner_or_assigned(
            session=obj,
            user_id=self.request.user.id,
            is_pharmacist=is_pharmacist(self.request.user),
        )
        return obj

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        return Response(
            ConsultationSessionSerializer(session, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        session = self.get_object()
        if session.status in (ConsultationSession.COMPLETED, ConsultationSession.CANCELLED):
            raise ValidationError({"detail": "Session đã đóng."})

        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        update_fields = ["updated_date"]

        if "firestore_conversation_id" in data:
            session.firestore_conversation_id = (data["firestore_conversation_id"] or "").strip()
            update_fields.append("firestore_conversation_id")
        if "need_text" in data and session.user_id == request.user.id:
            session.need_text = (data["need_text"] or "").strip()
            update_fields.append("need_text")
        if "context_json" in data and session.user_id == request.user.id:
            session.context_json = data["context_json"] or {}
            update_fields.append("context_json")

        session.updated_date = timezone.now()
        session.save(update_fields=update_fields)
        return Response(ConsultationSessionSerializer(session).data)

    @action(detail=True, methods=["post"], url_path="claim")
    def claim(self, request, pk=None):
        session = pharmacist_queue.claim_session(session_id=int(pk), pharmacist_id=request.user.id)
        return Response(ConsultationSessionSerializer(session).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        session = self.get_object()
        if session.status not in (
            ConsultationSession.WAITING_FOR_PROFESSIONAL,
            ConsultationSession.IN_PROGRESS,
        ):
            raise ValidationError({"detail": "Không thể hoàn thành session ở trạng thái hiện tại."})
        session.status = ConsultationSession.COMPLETED
        session.updated_date = timezone.now()
        session.save(update_fields=["status", "updated_date"])
        return Response(ConsultationSessionSerializer(session).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        session = self.get_object()
        if session.status in (ConsultationSession.COMPLETED, ConsultationSession.CANCELLED):
            raise ValidationError({"detail": "Session đã đóng."})
        uid = request.user.id
        if not (
            session.user_id == uid
            or session.pharmacist_id == uid
            or is_business_admin(request.user)
        ):
            raise PermissionDenied()
        session.status = ConsultationSession.CANCELLED
        session.updated_date = timezone.now()
        session.save(update_fields=["status", "updated_date"])
        return Response(ConsultationSessionSerializer(session).data)
