from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from storeApp.models import MedicineRequest
from storeApp.serializers_medicine_request import (
    MedicineRequestCreateSerializer,
    MedicineRequestSerializer,
)


class MedicineRequestViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "head", "options"]
    pagination_class = None

    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == "create":
            return MedicineRequestCreateSerializer
        return MedicineRequestSerializer

    def get_queryset(self):
        return MedicineRequest.objects.filter(
            user_id=self.request.user.id,
            active=True,
        ).order_by("-created_date", "-id")

    def get_object(self):
        obj = get_object_or_404(MedicineRequest.objects.all(), pk=self.kwargs["pk"], active=True)
        if obj.user_id != self.request.user.id:
            raise PermissionDenied()
        return obj

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save()
        body = MedicineRequestSerializer(lead, context={"request": request}).data
        body["notification_id"] = getattr(lead, "_notification_id", None)
        return Response(body, status=status.HTTP_201_CREATED)
