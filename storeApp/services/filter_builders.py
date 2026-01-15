"""
Filter Builders
Methods for building filter objects from extracted variants
"""
from collections import defaultdict
from django.db.models import Count, Q, Case, When, CharField, Value
from storeApp.services.filter_constants import (
    FILTER_CONFIGS,
    PRICE_RANGES,
    CATEGORY_TYPE_FILTER_CONFIGS,
    DEFAULT_FILTER_CONFIG,
    FILTER_VARIANT_MAP
)
from storeApp.services.filter_helpers import FilterHelpers


class FilterBuilders:
    """Builders for dynamic filter objects"""
    
    @staticmethod
    def build_filters(queryset, variants, category_slug=None, category=None, brand_ids_list=None, brands_dict=None):
        """
        Build filters structure with optimized queries (no N+1)
        Supports category-specific filter configuration
        """
        # Get category type
        if category:
            category_type = FilterHelpers.get_category_type_from_category(category)
        elif category_slug:
            category_type = FilterHelpers.get_category_type(category_slug)
        else:
            category_type = 'default'
        
        # Get filter config cho category type
        category_config = CATEGORY_TYPE_FILTER_CONFIGS.get(
            category_type,
            DEFAULT_FILTER_CONFIG
        )
        
        enabled_filters = category_config.get('enabled_filters', [])
        filter_priority = category_config.get('filter_priority', enabled_filters)
        
        filters = []
        
        # Build filters theo priority và enabled list
        # Use enumerate to assign priority based on position in filter_priority list
        for priority_index, filter_id in enumerate(filter_priority, start=1):
            if filter_id not in enabled_filters:
                continue
            
            if not FilterHelpers.has_variants(variants, filter_id):
                continue
            
            filter_obj = FilterBuilders.build_single_filter(
                queryset, variants, filter_id, brand_ids_list, brands_dict, priority=priority_index
            )
            if filter_obj:
                filters.append(filter_obj)
        
        return filters
    
    @staticmethod
    def build_filter_object(filter_id, options, variants, show_more=None, priority=None):
        """
        Helper method to build filter object from options
        Reduces code duplication across filter builders
        
        Args:
            filter_id: Filter identifier
            options: List of filter options
            variants: Variants dict
            show_more: Whether to show "show more" button
            priority: Priority number for sorting (lower = higher priority)
        """
        config = FILTER_CONFIGS.get(filter_id)
        if not config:
            return None
        
        if show_more is None:
            variant_key = FILTER_VARIANT_MAP.get(filter_id, '')
            variant_set = variants.get(variant_key, [])
            show_more = len(variant_set) > config['limit'] if config.get('limit') else False
        
        filter_obj = {
            'id': filter_id,
            'type': config['type'],
            'label': config['label'],
            'field': config['field'],
            'searchable': config['searchable'],
            'options': options,
            'defaultSelected': [],
            'showMore': show_more
        }
        
        # Add priority if provided
        if priority is not None:
            filter_obj['priority'] = priority
        
        return filter_obj
    
    @staticmethod
    def build_country_filter(queryset, variants, brand_ids_list, brands_dict):
        """Build country filter"""
        if not variants.get('countries') or not brand_ids_list:
            return None
        
        # Build country count map from Brand.country (optimized)
        country_to_brand_ids = defaultdict(list)
        for brand_id, (brand_name, country) in brands_dict.items():
            if country:
                country_to_brand_ids[country].append(brand_id)
        
        # Count products for each country
        country_count_map = {}
        for country, brand_ids_for_country in country_to_brand_ids.items():
            count = queryset.filter(medicine__brand_id__in=brand_ids_for_country).count()
            country_count_map[country] = count
        
        # Build options
        country_options = []
        limit = FILTER_CONFIGS['country']['limit']
        for country in sorted(variants['countries'])[:limit]:
            country_options.append({
                'value': country,
                'label': country,
                'count': country_count_map.get(country, 0)
            })
        
        return FilterBuilders.build_filter_object('country', country_options, variants)
    
    @staticmethod
    def build_brand_filter(queryset, variants, brand_ids_list, brands_dict):
        """Build brand filter"""
        if not variants.get('brands') or not brand_ids_list:
            return None
        
        # Get brand_ids and count products per brand_id for ALL brands
        brand_id_counts = queryset.exclude(
            Q(medicine__brand_id__isnull=True) | Q(medicine__brand_id=0)
        ).values('medicine__brand_id').annotate(count=Count('id'))
        
        # Build brand_count_map
        brand_count_map = {}
        for item in brand_id_counts:
            brand_id = item['medicine__brand_id']
            brand_name = brands_dict.get(brand_id, (None, None))[0]
            if brand_name:
                brand_count_map[brand_name] = item['count']
        
        # Build options with counts, sort by count descending
        brand_options = []
        for brand_name in variants['brands']:
            count = brand_count_map.get(brand_name, 0)
            if count > 0:
                brand_options.append({
                    'value': brand_name,
                    'label': brand_name,
                    'count': count
                })
        
        brand_options.sort(key=lambda x: (-x['count'], x['label']))
        
        limit = FILTER_CONFIGS['brand']['limit']
        brand_options = brand_options[:limit]
        
        return FilterBuilders.build_filter_object('brand', brand_options, variants)
    
    @staticmethod
    def build_price_range_filter(queryset, variants, brand_ids_list=None, brands_dict=None):
        """Build price range filter"""
        if not variants.get('priceRanges'):
            return None
        
        # Pre-compute price range counts if not already done
        if '_price_range_counts' not in variants:
            variants['_price_range_counts'] = FilterBuilders.compute_all_price_range_counts(
                queryset, variants['priceRanges']
            )
        
        price_range_counts = variants.get('_price_range_counts', {})
        price_options = []
        
        for price_range_key in sorted(variants['priceRanges']):
            count = price_range_counts.get(price_range_key)
            if count is None:
                count = FilterBuilders.count_by_price_range(queryset, price_range_key)
            
            price_options.append({
                'value': price_range_key,
                'label': PRICE_RANGES[price_range_key]['label'],
                'count': count
            })
        
        return FilterBuilders.build_filter_object('priceRange', price_options, variants, show_more=False)
    
    @staticmethod
    def build_variant_based_filter(filter_id, variants, variant_key, count_key):
        """
        Generic builder for filters that use pre-computed variant counts
        Used for: targetAudience, flavor, indication, skinType, medicineType, ingredients
        """
        variant_set = variants.get(variant_key, [])
        if not variant_set:
            return None
        
        counts = variants.get(count_key, {})
        config = FILTER_CONFIGS.get(filter_id)
        if not config:
            return None
        
        options = []
        limit = config.get('limit')
        sorted_variants = sorted(variant_set)
        
        if limit:
            sorted_variants = sorted_variants[:limit]
        
        for variant_value in sorted_variants:
            count = counts.get(variant_value, 0)
            if count > 0:
                options.append({
                    'value': variant_value,
                    'label': variant_value,
                    'count': count
                })
        
        if not options:
            return None
        
        return FilterBuilders.build_filter_object(filter_id, options, variants)
    
    @staticmethod
    def build_single_filter(queryset, variants, filter_id, brand_ids_list=None, brands_dict=None, priority=None):
        """
        Build a single filter based on filter_id using registry pattern
        
        Args:
            queryset: MedicineUnit queryset
            variants: Extracted variants dict
            filter_id: Filter identifier
            brand_ids_list: List of brand IDs
            brands_dict: Dict mapping brand_id -> (name, country)
            priority: Priority number for sorting (lower = higher priority)
        """
        # Filter builder registry
        FILTER_BUILDER_REGISTRY = {
            'country': FilterBuilders.build_country_filter,
            'brand': FilterBuilders.build_brand_filter,
            'priceRange': FilterBuilders.build_price_range_filter,
            'targetAudience': lambda q, v, b1, b2: FilterBuilders.build_variant_based_filter(
                'targetAudience', v, 'targetAudiences', '_target_audience_counts'
            ),
            'flavor': lambda q, v, b1, b2: FilterBuilders.build_variant_based_filter(
                'flavor', v, 'flavors', '_flavor_counts'
            ),
            'indication': lambda q, v, b1, b2: FilterBuilders.build_variant_based_filter(
                'indication', v, 'indications', '_indication_counts'
            ),
            'skinType': lambda q, v, b1, b2: FilterBuilders.build_variant_based_filter(
                'skinType', v, 'skinTypes', '_skin_type_counts'
            ),
            'medicineType': lambda q, v, b1, b2: FilterBuilders.build_variant_based_filter(
                'medicineType', v, 'medicineTypes', '_medicine_type_counts'
            ),
            'ingredients': lambda q, v, b1, b2: FilterBuilders.build_variant_based_filter(
                'ingredients', v, 'ingredients', '_ingredient_counts'
            ),
        }
        
        # Get builder from registry
        builder = FILTER_BUILDER_REGISTRY.get(filter_id)
        if not builder:
            return None
        
        # Call builder with appropriate parameters
        filter_obj = None
        if filter_id in ['country', 'brand']:
            filter_obj = builder(queryset, variants, brand_ids_list, brands_dict)
        elif filter_id == 'priceRange':
            filter_obj = builder(queryset, variants)
        else:
            # Variant-based filters don't need queryset or brand data
            filter_obj = builder(queryset, variants, None, None)
        
        # Add priority if provided and filter_obj exists
        if filter_obj and priority is not None:
            filter_obj['priority'] = priority
        
        return filter_obj
    
    @staticmethod
    def compute_all_price_range_counts(queryset, price_range_keys):
        """
        Compute counts for all price ranges in a single optimized query
        Returns dict mapping price_range_key -> count
        """
        price_range_counts = {}
        
        if not price_range_keys:
            return price_range_counts
        
        # Use Case/When to categorize prices into ranges in one query
        when_conditions = []
        for range_key in price_range_keys:
            range_config = PRICE_RANGES.get(range_key)
            if not range_config:
                continue
            
            min_price = range_config['min']
            max_price = range_config['max']
            
            if max_price is None:
                when_conditions.append(
                    When(price_value__gte=min_price, then=Value(range_key))
                )
            else:
                when_conditions.append(
                    When(price_value__gte=min_price, price_value__lt=max_price, then=Value(range_key))
                )
        
        if not when_conditions:
            return price_range_counts
        
        # Annotate queryset with price range category
        annotated_queryset = queryset.exclude(price_value=0).annotate(
            price_range=Case(*when_conditions, default=None, output_field=CharField())
        )
        
        # Count by price range
        range_counts = annotated_queryset.values('price_range').annotate(
            count=Count('id')
        ).filter(price_range__isnull=False)
        
        # Build result dict
        for item in range_counts:
            price_range_counts[item['price_range']] = item['count']
        
        # Fill in zeros for ranges with no products
        for range_key in price_range_keys:
            if range_key not in price_range_counts:
                price_range_counts[range_key] = 0
        
        return price_range_counts
    
    @staticmethod
    def count_by_price_range(queryset, price_range_key):
        """
        Count products in a price range (legacy method, kept for backward compatibility)
        For better performance, use compute_all_price_range_counts instead
        """
        range_config = PRICE_RANGES.get(price_range_key)
        if not range_config:
            return 0
        
        min_price = range_config['min']
        max_price = range_config['max']
        
        if max_price is None:
            return queryset.filter(price_value__gte=min_price).count()
        return queryset.filter(price_value__gte=min_price, price_value__lt=max_price).count()
