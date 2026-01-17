"""
Dynamic Filters Service Layer
Main orchestration service for dynamic filters feature
"""
from django.core.cache import cache
from storeApp.services.filter_constants import (
    CACHE_TIMEOUT,
    CACHE_PREFIX,
    LARGE_CATEGORY_THRESHOLD
)
from storeApp.services.filter_helpers import FilterHelpers
from storeApp.services.filter_extractors import FilterExtractors
from storeApp.services.filter_builders import FilterBuilders


class DynamicFiltersService:
    """
    Service layer for dynamic filters
    Main orchestration class that coordinates helpers, extractors, and builders
    """
    
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
        cache_key = f'{CACHE_PREFIX}:{category_slug}'
        
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
        product_count = queryset.count()
        
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
            brand_ids_list, brands_dict = FilterHelpers.get_brand_data(queryset)
            variants = FilterExtractors.extract_variants(queryset, brand_ids_list, brands_dict)
            
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
        if include_variants:
            if not include_counts:
                # Remove count fields from variants
                variants = response_data.get('variants', {})
                variants_without_counts = {k: v for k, v in variants.items() 
                                         if not k.startswith('_')}
                response_data['variants'] = variants_without_counts
        else:
            # Remove variants entirely
            response_data.pop('variants', None)
        
        return response_data
    
    @staticmethod
    def invalidate_cache(category_slug: str = None):
        """Invalidate cache for dynamic filters"""
        if category_slug:
            cache_key = f'{CACHE_PREFIX}:{category_slug}'
            cache.delete(cache_key)
