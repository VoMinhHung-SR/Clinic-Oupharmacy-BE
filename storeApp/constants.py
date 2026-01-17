"""
General constants for storeApp
Note: Filter-related constants have been moved to storeApp/services/filter_constants.py
"""
from django.conf import settings

# Cache configuration (general)
CACHE_TIMEOUT = getattr(settings, 'DYNAMIC_FILTERS_CACHE_TTL', 3600)  # 1 hour
CACHE_PREFIX = 'dynamic_filters'
