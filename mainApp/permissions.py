from rest_framework import permissions

from mainApp.authz import is_business_admin, is_system_superadmin


class OwnerPermission(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return bool(request.user and request.user == obj.user)


class UserPermission(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return bool(request.user and request.user == obj)


class AdminPermission(permissions.IsAuthenticated):
    """System superadmin only (is_superuser). Not business is_admin."""

    def has_permission(self, request, view):
        return is_system_superadmin(request.user)


class IsBusinessAdmin(permissions.BasePermission):
    """Clinic FE + store business APIs + Jazzmin login: is_admin or is_superuser. Not Django is_staff."""

    def has_permission(self, request, view):
        return is_business_admin(request.user)


class OwnerExaminationPermission(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return bool(request.user and request.user == obj.examination.user)