"""Shared store catalog constants (non dynamic-filters)."""
from django.conf import settings

LARGE_CATEGORY_THRESHOLD = getattr(settings, "LARGE_CATEGORY_THRESHOLD", 1000)
