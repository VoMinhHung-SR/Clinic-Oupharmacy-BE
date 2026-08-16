"""Signed storefront preview tokens (D-19). No DB table; expiry is the revoke."""

from __future__ import annotations

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

PREVIEW_SALT = "campaign-preview-v1"
PREVIEW_MAX_AGE = 7200


def sign_campaign_preview(campaign) -> str:
    signer = TimestampSigner(salt=PREVIEW_SALT)
    return signer.sign(f"{campaign.pk}:{campaign.slug}")


def unsign_campaign_preview(token: str | None) -> tuple[int, str] | None:
    if token is None or not str(token).strip():
        return None
    signer = TimestampSigner(salt=PREVIEW_SALT)
    try:
        value = signer.unsign(str(token).strip(), max_age=PREVIEW_MAX_AGE)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    try:
        id_str, slug = value.split(":", 1)
        pk = int(id_str)
    except (ValueError, TypeError):
        return None
    if not slug:
        return None
    return pk, slug
