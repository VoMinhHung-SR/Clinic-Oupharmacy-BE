from rest_framework.permissions import BasePermission, IsAuthenticated

from mainApp.authz import is_business_admin
from mainApp.constant import ROLE_PHARMACIST


def user_role_name(user) -> str | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    role = getattr(user, "role", None)
    return getattr(role, "name", None) if role else None


def is_pharmacist(user) -> bool:
    return user_role_name(user) == ROLE_PHARMACIST or is_business_admin(user)


class IsPharmacist(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_pharmacist(request.user))


class IsAuthenticatedUser(IsAuthenticated):
    """Alias for clarity on customer consultation endpoints."""

    pass
