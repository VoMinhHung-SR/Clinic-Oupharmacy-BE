"""Guest cart session via X-Guest-Session header (UUID v4)."""

import re
import uuid
from typing import Optional

from django.http import HttpRequest

GUEST_SESSION_HEADER = "HTTP_X_GUEST_SESSION"
GUEST_SESSION_HEADER_ALT = "X-Guest-Session"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def normalize_guest_session_id(raw) -> Optional[str]:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if not value or not _UUID_RE.match(value):
        return None
    return value


def guest_session_id_from_request(request: HttpRequest) -> Optional[str]:
    raw = request.META.get(GUEST_SESSION_HEADER) or request.headers.get(GUEST_SESSION_HEADER_ALT)
    return normalize_guest_session_id(raw)


def new_guest_session_id() -> str:
    return str(uuid.uuid4())


def guest_session_uuid(raw) -> uuid.UUID:
    """Coerce normalized header value to UUID for ORM filters/creates."""
    if isinstance(raw, uuid.UUID):
        return raw
    normalized = normalize_guest_session_id(raw)
    if not normalized:
        raise ValueError("Invalid guest session id")
    return uuid.UUID(normalized)
