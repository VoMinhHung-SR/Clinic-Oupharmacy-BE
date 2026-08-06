"""DRF permissions for Campaign admin API."""

from rest_framework.permissions import BasePermission


class CanViewCampaign(BasePermission):
    """Staff with storeApp.campaign_view or campaign_manage."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_staff:
            return False
        if user.is_superuser:
            return True
        return user.has_perm("storeApp.campaign_view") or user.has_perm("storeApp.campaign_manage")


class CanManageCampaign(BasePermission):
    """Staff with storeApp.campaign_manage."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_staff:
            return False
        if user.is_superuser:
            return True
        return user.has_perm("storeApp.campaign_manage")
