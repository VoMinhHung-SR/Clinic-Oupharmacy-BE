"""Custom OAuth2 validator: enforce max age for refresh tokens (DOT default ignores age on validate)."""

from datetime import timedelta

from django.utils import timezone
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauth2_provider.settings import oauth2_settings


class OUPharmacyOAuth2Validator(OAuth2Validator):
    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        ok = super().validate_refresh_token(refresh_token, client, request, *args, **kwargs)
        if not ok:
            return False

        max_age = oauth2_settings.REFRESH_TOKEN_EXPIRE_SECONDS
        if not max_age:
            return True

        rt = getattr(request, "refresh_token_instance", None)
        if rt is None:
            return False

        delta = max_age if isinstance(max_age, timedelta) else timedelta(seconds=max_age)
        if rt.created < timezone.now() - delta:
            return False

        return True
