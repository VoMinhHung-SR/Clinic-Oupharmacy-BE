"""
Dynamic Filters Service Layer
Main orchestration service for dynamic filters feature
"""
import copy
from django.core.cache import cache
from storeApp.services.filter_constants import (
    CACHE_TIMEOUT,
    CACHE_PREFIX,
    LARGE_CATEGORY_THRESHOLD,
    CATEGORY_TYPE_FILTER_CONFIGS,
    DEFAULT_FILTER_CONFIG,
)
from storeApp.services.filter_helpers import FilterHelpers
from storeApp.services.filter_extractors import FilterExtractors
from storeApp.services.filter_builders import FilterBuilders
from storeApp.services.variant_listing import count_distinct_products


class DynamicFiltersService:
    """
    Service layer for dynamic filters
    Main orchestration class that coordinates helpers, extractors, and builders
    """
    CACHE_VERSION_KEY = f"{CACHE_PREFIX}:version"

    @staticmethod
    def _cache_version():
        return cache.get(DynamicFiltersService.CACHE_VERSION_KEY) or 1

    @staticmethod
    def _cache_key(category_slug: str) -> str:
        return f"{CACHE_PREFIX}:v{DynamicFiltersService._cache_version()}:{category_slug}"

    @staticmethod
    def _enabled_filters_for_category(category):
        category_type = FilterHelpers.get_category_type_from_category(category)
        category_config = CATEGORY_TYPE_FILTER_CONFIGS.get(
            category_type,
            DEFAULT_FILTER_CONFIG,
        )
        return category_config.get("enabled_filters", [])
    
    @staticmethod
    def get_category_filters(category_slug: str, use_cache: bool = True, 
                            include_variants: bool = True, include_counts: bool = True):
        """
        Get dynamic filters for a category
        
        Args:
            category_slug: Category slug or path_slug
            use_cache: Whether to use cache (default: True)
            include_variants: Whether to include variants in response (default: True)
            include_counts: Whether to include count fields in variants (default: True)
        
        Returns:
            dict: Filters response with categorySlug, categoryName, productCount, variants (optional), filters
            None: If category not found
        """
        cache_key = DynamicFiltersService._cache_key(category_slug)
        
        # Try to get from cache (cache always stores full data)
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                # Apply response filtering if needed
                return DynamicFiltersService._filter_response_data(
                    cached_data, include_variants, include_counts
                )
        
        # Get category
        category = FilterHelpers.get_category_from_slug(category_slug)
        if not category:
            return None
        
        # Get queryset
        queryset = FilterHelpers.get_category_queryset(category)
        product_count = count_distinct_products(queryset)
        
        # Get subcategories (always needed for navigation)
        subcategories = FilterHelpers.get_immediate_subcategories(category)
        has_subcategories = len(subcategories) > 0
        
        # Check if category is too large - skip expensive filter extraction
        # This prevents long processing time for large categories (5000+ products)
        if product_count > LARGE_CATEGORY_THRESHOLD:
            # Build response without filters (skip expensive extraction)
            response_data = {
                'categorySlug': category.path_slug or category.slug,
                'categoryName': category.path or category.name,
                'productCount': product_count,
                'hasSubcategories': has_subcategories,
                'subcategories': subcategories,
                'variants': None,  # Not extracted for large categories
                'filters': None,  # Not extracted for large categories (UI should not render filters)
                'overLimit': True  # Flag to indicate category is over limit
            }
        else:
            # Normal flow: extract filters and variants for categories <= 1000 products
            # Extract variants with pre-computed brand data
            enabled_filters = DynamicFiltersService._enabled_filters_for_category(category)
            brand_ids_list, brands_dict = FilterHelpers.get_brand_data(queryset)
            variants = FilterExtractors.extract_variants(
                queryset,
                brand_ids_list,
                brands_dict,
                enabled_filters=enabled_filters,
            )
            
            # Pre-compute price range counts if price ranges exist
            if variants.get('priceRanges'):
                variants['_price_range_counts'] = FilterBuilders.compute_all_price_range_counts(
                    queryset, variants['priceRanges']
                )
            
            # Build filters với category object and pre-computed data
            filters = FilterBuilders.build_filters(
                queryset, 
                variants, 
                category_slug=category_slug,
                category=category,
                brand_ids_list=brand_ids_list,
                brands_dict=brands_dict
            )
            
            # Build response (always include full data, filter later)
            response_data = {
                'categorySlug': category.path_slug or category.slug,
                'categoryName': category.path or category.name,
                'productCount': product_count,
                'hasSubcategories': has_subcategories,
                'subcategories': subcategories,  # Include for navigation
                'variants': variants,  # Always include full variants for cache
                'filters': filters,
                'overLimit': False  # Flag to indicate category is within limit
            }
        
        # Cache the full response (always cache full data for flexibility)
        # Must cache BEFORE filtering response for client
        if use_cache:
            cache.set(cache_key, response_data.copy(), timeout=CACHE_TIMEOUT)
        
        # Apply response filtering and return
        return DynamicFiltersService._filter_response_data(
            response_data, include_variants, include_counts
        )
    
    @staticmethod
    def _filter_response_data(response_data, include_variants, include_counts):
        """
        Filter response data based on include_variants and include_counts flags
        Used for both cached and fresh responses
        """
        # Never mutate cached/original response object.
        payload = copy.deepcopy(response_data)
        if include_variants:
            if not include_counts:
                # Remove count fields from variants
                variants = payload.get('variants') or {}
                variants_without_counts = {k: v for k, v in variants.items() 
                                         if not k.startswith('_')}
                payload['variants'] = variants_without_counts
        else:
            # Remove variants entirely
            payload.pop('variants', None)
        
        return payload
    
    @staticmethod
    def invalidate_cache(category_slug: str = None):
        """Invalidate cache for dynamic filters (one category or all)."""
        if category_slug:
            cache.delete(DynamicFiltersService._cache_key(category_slug))
            return
        DynamicFiltersService.invalidate_all_cache()

    @staticmethod
    def invalidate_all_cache():
        """Bump cache version so all facet snapshots are refreshed."""
        version = DynamicFiltersService._cache_version()
        cache.set(DynamicFiltersService.CACHE_VERSION_KEY, version + 1, timeout=None)
