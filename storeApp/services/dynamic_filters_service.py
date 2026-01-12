"""
Dynamic Filters Service Layer
Business logic for dynamic filters feature
"""
import logging
from django.db import models
from django.db.models import Count, Min, Max, Avg, Q
from django.core.cache import cache
from django.conf import settings
from mainApp.models import Category, MedicineUnit
from storeApp.models import Brand

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TIMEOUT = getattr(settings, 'DYNAMIC_FILTERS_CACHE_TTL', 3600)  # 1 hour
CACHE_PREFIX = 'dynamic_filters'

# Filter configuration
FILTER_CONFIGS = {
    'brandOrigin': {
        'field': 'origin',
        'label': 'Xuất xứ thương hiệu',
        'type': 'checkbox',
        'searchable': True,
        'limit': 20
    },
    'manufacturer': {
        'field': 'manufacturer',
        'label': 'Nước sản xuất',
        'type': 'checkbox',
        'searchable': False,
        'limit': 20
    },
    'brand': {
        'field': 'brand',
        'label': 'Thương hiệu',
        'type': 'checkbox',
        'searchable': True,
        'limit': 20
    },
    'priceRange': {
        'field': 'price_value',
        'label': 'Giá bán',
        'type': 'checkbox',
        'searchable': False,
        'limit': None
    }
}

# Price range configuration
PRICE_RANGES = {
    'under_100k': {
        'label': 'Dưới 100.000₫',
        'min': 0,
        'max': 100000
    },
    '100k_to_300k': {
        'label': '100.000₫ - 300.000₫',
        'min': 100000,
        'max': 300000
    },
    '300k_to_500k': {
        'label': '300.000₫ - 500.000₫',
        'min': 300000,
        'max': 500000
    },
    'over_500k': {
        'label': 'Trên 500.000₫',
        'min': 500000,
        'max': None
    }
}


class DynamicFiltersService:
    """
    Service layer for dynamic filters
    Handles all business logic for extracting and building filters
    """
    
    @staticmethod
    def get_category_filters(category_slug: str, use_cache: bool = True):
        """
        Get dynamic filters for a category
        
        Args:
            category_slug: Category slug or path_slug
            use_cache: Whether to use cache (default: True)
        
        Returns:
            dict: Filters response with categorySlug, categoryName, productCount, variants, filters
            None: If category not found
        """
        cache_key = f'{CACHE_PREFIX}:{category_slug}'
        
        # Try to get from cache
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f'Cache hit for category: {category_slug}')
                return cached_data
        
        # Get category
        category = DynamicFiltersService._get_category_from_slug(category_slug)
        if not category:
            logger.warning(f'Category not found: {category_slug}')
            return None
        
        # Get queryset
        queryset = DynamicFiltersService._get_category_queryset(category)
        product_count = queryset.count()
        
        # Extract variants
        variants = DynamicFiltersService._extract_variants(queryset)
        
        # Build filters
        filters = DynamicFiltersService._build_filters(queryset, variants)
        
        # Build response
        response_data = {
            'categorySlug': category.path_slug or category.slug,
            'categoryName': category.path or category.name,
            'productCount': product_count,
            'variants': variants,
            'filters': filters
        }
        
        # Cache the response
        if use_cache:
            cache.set(cache_key, response_data, timeout=CACHE_TIMEOUT)
            logger.debug(f'Cached filters for category: {category_slug}')
        
        return response_data
    
    @staticmethod
    def _get_category_from_slug(category_slug: str):
        """Get category from slug"""
        return Category.objects.using('default').filter(
            active=True
        ).filter(
            models.Q(path_slug__iexact=category_slug) | 
            models.Q(slug__iexact=category_slug)
        ).first()
    
    @staticmethod
    def _get_category_queryset(category):
        """Get MedicineUnit queryset for category (including subcategories)"""
        category_path_slug = category.path_slug or category.slug
        
        # Get all category IDs (including subcategories)
        category_ids = [category.id]
        subcategories = Category.objects.using('default').filter(
            active=True,
            path_slug__istartswith=f"{category_path_slug}/"
        ).values_list('id', flat=True)
        category_ids.extend(list(subcategories))
        
        # Get MedicineUnits in these categories
        return MedicineUnit.objects.using('default').filter(
            active=True,
            is_published=True,
            category_id__in=category_ids
        ).select_related('medicine', 'category')
    
    @staticmethod
    def _extract_variants(queryset):
        """
        Extract variants from queryset with optimized queries
        Returns: dict with brands, origins, manufacturers, priceRanges, priceStats
        """
        variants = {
            'brands': [],
            'origins': [],
            'manufacturers': [],
            'priceRanges': [],
            'priceStats': {}
        }
        
        # Extract unique origins (optimized)
        origins = queryset.exclude(
            Q(origin__isnull=True) | Q(origin='')
        ).values_list('origin', flat=True).distinct()
        variants['origins'] = sorted([o for o in origins if o])
        
        # Extract unique manufacturers (optimized)
        manufacturers = queryset.exclude(
            Q(manufacturer__isnull=True) | Q(manufacturer='')
        ).values_list('manufacturer', flat=True).distinct()
        variants['manufacturers'] = sorted([m for m in manufacturers if m])
        
        # Extract brands (optimized with prefetch)
        brand_ids = queryset.exclude(
            Q(medicine__brand_id__isnull=True) | Q(medicine__brand_id=0)
        ).values_list('medicine__brand_id', flat=True).distinct()
        
        if brand_ids:
            brands = Brand.objects.using('default').filter(
                id__in=brand_ids,
                active=True
            ).values_list('name', flat=True)
            variants['brands'] = sorted([b for b in brands if b])
        
        # Calculate price stats (single query)
        price_stats = queryset.exclude(price_value=0).aggregate(
            min=Min('price_value'),
            max=Max('price_value'),
            avg=Avg('price_value')
        )
        
        if price_stats['min'] is not None:
            # Calculate median
            all_prices = list(queryset.exclude(price_value=0).values_list('price_value', flat=True))
            median = DynamicFiltersService._calculate_median(all_prices)
            
            variants['priceStats'] = {
                'min': int(price_stats['min']),
                'max': int(price_stats['max']),
                'average': float(price_stats['avg']) if price_stats['avg'] else 0,
                'median': median
            }
            
            # Generate price ranges
            variants['priceRanges'] = DynamicFiltersService._generate_price_ranges(
                price_stats['min'],
                price_stats['max']
            )
        
        return variants
    
    @staticmethod
    def _calculate_median(values):
        """Calculate median from values"""
        if not values:
            return 0
        values_list = sorted([v for v in values if v])
        n = len(values_list)
        if n == 0:
            return 0
        if n % 2 == 0:
            return (values_list[n//2 - 1] + values_list[n//2]) / 2
        return values_list[n//2]
    
    @staticmethod
    def _generate_price_ranges(min_price, max_price):
        """Generate price range keys based on min/max prices"""
        ranges = []
        
        if min_price < 100000:
            ranges.append('under_100k')
        if min_price < 300000 or max_price >= 100000:
            ranges.append('100k_to_300k')
        if min_price < 500000 or max_price >= 300000:
            ranges.append('300k_to_500k')
        if max_price >= 500000:
            ranges.append('over_500k')
        
        return sorted(set(ranges))
    
    @staticmethod
    def _build_filters(queryset, variants):
        """
        Build filters structure with optimized queries (no N+1)
        Uses aggregation to get counts in single queries
        """
        filters = []
        
        # Filter: Xuất xứ thương hiệu (Brand Origin) - Optimized
        if variants['origins']:
            # Get counts in single query using aggregation
            origin_counts = queryset.exclude(
                Q(origin__isnull=True) | Q(origin='')
            ).values('origin').annotate(
                count=Count('id')
            ).order_by('-count')[:FILTER_CONFIGS['brandOrigin']['limit']]
            
            origin_count_map = {item['origin']: item['count'] for item in origin_counts}
            
            origin_options = []
            for origin in sorted(variants['origins'])[:FILTER_CONFIGS['brandOrigin']['limit']]:
                origin_options.append({
                    'value': origin,
                    'label': origin,
                    'count': origin_count_map.get(origin, 0)
                })
            
            config = FILTER_CONFIGS['brandOrigin']
            filters.append({
                'id': 'brandOrigin',
                'type': config['type'],
                'label': config['label'],
                'field': config['field'],
                'searchable': config['searchable'],
                'options': origin_options,
                'defaultSelected': [],
                'showMore': len(variants['origins']) > config['limit']
            })
        
        # Filter: Nước sản xuất (Manufacturer) - Optimized
        if variants['manufacturers']:
            # Get counts in single query using aggregation
            manufacturer_counts = queryset.exclude(
                Q(manufacturer__isnull=True) | Q(manufacturer='')
            ).values('manufacturer').annotate(
                count=Count('id')
            ).order_by('-count')[:FILTER_CONFIGS['manufacturer']['limit']]
            
            manufacturer_count_map = {item['manufacturer']: item['count'] for item in manufacturer_counts}
            
            manufacturer_options = []
            for manufacturer in sorted(variants['manufacturers'])[:FILTER_CONFIGS['manufacturer']['limit']]:
                manufacturer_options.append({
                    'value': manufacturer,
                    'label': manufacturer,
                    'count': manufacturer_count_map.get(manufacturer, 0)
                })
            
            config = FILTER_CONFIGS['manufacturer']
            filters.append({
                'id': 'manufacturer',
                'type': config['type'],
                'label': config['label'],
                'field': config['field'],
                'searchable': config['searchable'],
                'options': manufacturer_options,
                'defaultSelected': [],
                'showMore': len(variants['manufacturers']) > config['limit']
            })
        
        # Filter: Thương hiệu (Brand) - Optimized
        if variants['brands']:
            # Get brand counts in single query using aggregation
            brand_counts = queryset.exclude(
                Q(medicine__brand_id__isnull=True) | Q(medicine__brand_id=0)
            ).values('medicine__brand__name').annotate(
                count=Count('id')
            ).order_by('-count')[:FILTER_CONFIGS['brand']['limit']]
            
            brand_count_map = {item['medicine__brand__name']: item['count'] for item in brand_counts if item['medicine__brand__name']}
            
            brand_options = []
            for brand_name in sorted(variants['brands'])[:FILTER_CONFIGS['brand']['limit']]:
                brand_options.append({
                    'value': brand_name,
                    'label': brand_name,
                    'count': brand_count_map.get(brand_name, 0)
                })
            
            config = FILTER_CONFIGS['brand']
            filters.append({
                'id': 'brand',
                'type': config['type'],
                'label': config['label'],
                'field': config['field'],
                'searchable': config['searchable'],
                'options': brand_options,
                'defaultSelected': [],
                'showMore': len(variants['brands']) > config['limit']
            })
        
        # Filter: Giá bán (Price Range) - Optimized
        if variants['priceRanges']:
            price_options = []
            for price_range_key in sorted(variants['priceRanges']):
                count = DynamicFiltersService._count_by_price_range(queryset, price_range_key)
                price_options.append({
                    'value': price_range_key,
                    'label': PRICE_RANGES[price_range_key]['label'],
                    'count': count
                })
            
            config = FILTER_CONFIGS['priceRange']
            filters.append({
                'id': 'priceRange',
                'type': config['type'],
                'label': config['label'],
                'field': config['field'],
                'searchable': config['searchable'],
                'options': price_options,
                'defaultSelected': [],
                'showMore': False
            })
        
        return filters
    
    @staticmethod
    def _count_by_price_range(queryset, price_range_key):
        """Count products in a price range"""
        range_config = PRICE_RANGES.get(price_range_key)
        if not range_config:
            return 0
        
        min_price = range_config['min']
        max_price = range_config['max']
        
        if max_price is None:
            return queryset.filter(price_value__gte=min_price).count()
        return queryset.filter(price_value__gte=min_price, price_value__lt=max_price).count()
    
    @staticmethod
    def invalidate_cache(category_slug: str = None):
        """
        Invalidate cache for dynamic filters
        
        Args:
            category_slug: Category slug to invalidate. If None, invalidate all (not implemented)
        """
        if category_slug:
            cache_key = f'{CACHE_PREFIX}:{category_slug}'
            cache.delete(cache_key)
            logger.info(f'Invalidated cache for category: {category_slug}')
        else:
            # TODO: Implement pattern-based cache invalidation if using Redis
            logger.warning('Invalidating all filters cache not implemented')
