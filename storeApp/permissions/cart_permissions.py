from rest_framework.permissions import BasePermission

from storeApp.services.guest_session import guest_session_id_from_request


class IsAuthenticatedOrGuestCart(BasePermission):
    """
    Allow OAuth2-authenticated users or anonymous clients with valid X-Guest-Session.
    Sets request.guest_session_id when guest path is used.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            request.guest_session_id = None
            return True
        guest_id = guest_session_id_from_request(request)
        if guest_id:
            request.guest_session_id = guest_id
            return True
        return False
