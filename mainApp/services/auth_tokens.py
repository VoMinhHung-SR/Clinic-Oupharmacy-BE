"""OAuth2 token lifecycle helpers (django-oauth-toolkit)."""

from oauth2_provider.models import AccessToken, RefreshToken


def revoke_oauth2_tokens_for_user(user):
    """
    Remove all AccessToken and RefreshToken rows for this user so existing
    access/refresh tokens stop working after password change or reset.
    """
    if user is None or not getattr(user, "pk", None):
        return
    RefreshToken.objects.filter(user=user).delete()
    AccessToken.objects.filter(user=user).delete()
