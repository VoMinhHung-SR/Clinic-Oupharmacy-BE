"""
Versioned public campaign cache (P6-T2 / FR-09 / NFR-01).

Reuses django.core.cache like search facets: short TTL plus version bump on mutate.
"""
from __future__ import annotations

import hashlib
import json
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("storeApp.campaign")

CACHE_PREFIX = "store_campaign_public"
CACHE_TIMEOUT = getattr(settings, "CAMPAIGN_PUBLIC_CACHE_TTL", 60)
CACHE_VERSION_KEY = f"{CACHE_PREFIX}:version"
NOT_FOUND_COUNTER_TTL = 86400


def cache_version() -> int:
    return cache.get(CACHE_VERSION_KEY) or 1


def invalidate_public_campaign_cache() -> int:
    version = cache_version() + 1
    cache.set(CACHE_VERSION_KEY, version, timeout=None)
    logger.info("campaign_cache_invalidated version=%s", version)
    return version


def _cache_key(kind: str, extra=None) -> str:
    payload = json.dumps({"k": kind, "x": extra}, sort_keys=True, default=str)
    digest = hashlib.md5(payload.encode()).hexdigest()[:16]
    return f"{CACHE_PREFIX}:v{cache_version()}:{digest}"


def get_cached(kind: str, extra=None):
    return cache.get(_cache_key(kind, extra))


def set_cached(kind: str, value, extra=None, timeout=None):
    cache.set(_cache_key(kind, extra), value, timeout=timeout if timeout is not None else CACHE_TIMEOUT)
    return value


def log_campaign_transition(
    *,
    campaign_id,
    from_status,
    to_status,
    actor_user_id=None,
    source="api",
):
    logger.info(
        "campaign_transition campaign_id=%s from=%s to=%s actor=%s source=%s",
        campaign_id,
        from_status,
        to_status,
        actor_user_id,
        source,
    )


def record_public_slug_404(slug: str) -> int:
    logger.info("campaign_public_404 slug=%s", slug or "")
    key = f"{CACHE_PREFIX}:404:{slug or '_'}"
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=NOT_FOUND_COUNTER_TTL)
        return 1


def public_slug_404_count(slug: str) -> int:
    return cache.get(f"{CACHE_PREFIX}:404:{slug or '_'}") or 0
