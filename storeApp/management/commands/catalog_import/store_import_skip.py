"""Skip scrape-error landing categories (e.g. Cloudflare 5xx pages)."""

from __future__ import annotations

# L0 slug written by scraper when PDP returned Cloudflare/5xx HTML.
DEFAULT_SKIP_L0_SLUGS = frozenset(
    {
        "5xx-error-landing",
    }
)

DEFAULT_SKIP_L0_NAME_MARKERS = (
    "cloudflare.com",
    "cloudflare",
)


def should_skip_category_array(category_array: list | None) -> bool:
    """
    True when the row's L0 category is a scrape error page, not a real catalog node.
    Example: [{"name":"cloudflare.com","slug":"5xx-error-landing"}]
    """
    if not category_array:
        return False
    first = category_array[0]
    if not isinstance(first, dict):
        return False

    slug = str(first.get("slug") or "").strip().lower()
    name = str(first.get("name") or "").strip().lower()

    if slug in DEFAULT_SKIP_L0_SLUGS:
        return True
    for marker in DEFAULT_SKIP_L0_NAME_MARKERS:
        if marker in slug or marker in name:
            return True
    return False
