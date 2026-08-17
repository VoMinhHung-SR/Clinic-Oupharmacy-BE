"""DRF permissions for Campaign admin API."""

from rest_framework.permissions import BasePermission

from mainApp.authz import is_business_admin


class CanViewCampaign(BasePermission):
    """Business admin (is_admin) or system superuser. Not is_staff-only."""

    def has_permission(self, request, view):
        return is_business_admin(request.user)


class CanManageCampaign(BasePermission):
    """Same gate as view in v1: business admin owns campaign lifecycle (Jazzmin + REST)."""

    def has_permission(self, request, view):
        return is_business_admin(request.user)
