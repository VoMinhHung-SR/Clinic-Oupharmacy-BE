"""
Dynamic Filters Service Layer
Business logic for dynamic filters feature
"""
import logging
from collections import defaultdict
from django.db import models
from django.db.models import Count, Min, Max, Avg, Q
from django.core.cache import cache
from mainApp.models import Category, MedicineUnit, Medicine
from storeApp.models import Brand
from storeApp.services.filter_constants import (
    CACHE_TIMEOUT,
    CACHE_PREFIX,
    FILTER_CONFIGS,
    PRICE_RANGES,
    CATEGORY_TYPE_FILTER_CONFIGS,
    DEFAULT_FILTER_CONFIG,
    FILTER_VARIANT_MAP,
    TARGET_AUDIENCE_PATTERNS,
    INDICATION_KEYWORDS,
    SPECIFICATION_KEYS
)

logger = logging.getLogger(__name__)


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
        
        # Extract variants with pre-computed brand data
        brand_ids_list, brands_dict = DynamicFiltersService._get_brand_data(queryset)
        variants = DynamicFiltersService._extract_variants(queryset, brand_ids_list, brands_dict)
        
        # Build filters với category object and pre-computed data
        filters = DynamicFiltersService._build_filters(
            queryset, 
            variants, 
            category_slug=category_slug,
            category=category,
            brand_ids_list=brand_ids_list,
            brands_dict=brands_dict
        )
        
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
    def _get_root_category(category_slug: str = None, category=None):
        """
        Lấy root category (level = 0) từ database
        
        Args:
            category_slug: Category slug (optional)
            category: Category object (optional)
        
        Returns:
            Category: Root category object hoặc None
        """
        root_slug = None
        
        # Nếu đã có category object
        if category:
            # Nếu đã là root category (level = 0), return luôn
            if category.level == 0:
                return category
            
            # Lấy root slug từ path_slug (nhanh nhất, không cần query thêm)
            if category.path_slug:
                root_slug = category.path_slug.split('/')[0]
            elif category.slug:
                root_slug = category.slug
        
        # Nếu chỉ có category_slug, lấy root slug từ đó
        elif category_slug:
            root_slug = category_slug.split('/')[0]
        
        # Query root category từ database (level = 0, parent = None)
        if root_slug:
            return Category.objects.using('default').filter(
                active=True,
                level=0,
                parent__isnull=True,
                slug=root_slug
            ).first()
        
        return None
    
    @staticmethod
    def _get_category_type_from_root_slug(root_slug: str):
        """
        Map root category slug sang category type
        Logic: Dựa vào slug pattern để xác định type
        """
        if not root_slug:
            return 'default'
        
        slug_lower = root_slug.lower()
        
        if 'thuoc' in slug_lower:
            return 'medicine'
        elif 'duoc-mi-pham' in slug_lower or 'cosmetics' in slug_lower:
            return 'cosmetics'
        elif 'thuc-pham-chuc-nang' in slug_lower or 'supplements' in slug_lower:
            return 'supplements'
        
        return 'default'
    
    @staticmethod
    def _get_category_type(category_slug: str):
        """Xác định category type từ slug"""
        if not category_slug:
            return 'default'
        
        root_category = DynamicFiltersService._get_root_category(category_slug=category_slug)
        if not root_category:
            return 'default'
        
        return DynamicFiltersService._get_category_type_from_root_slug(root_category.slug)
    
    @staticmethod
    def _get_category_type_from_category(category):
        """Xác định category type từ Category object"""
        if not category:
            return 'default'
        
        root_category = DynamicFiltersService._get_root_category(category=category)
        if not root_category:
            return 'default'
        
        return DynamicFiltersService._get_category_type_from_root_slug(root_category.slug)
    
    @staticmethod
    def _has_variants(variants, filter_id):
        """Check xem filter có variants không"""
        variant_key = FILTER_VARIANT_MAP.get(filter_id)
        if not variant_key:
            return False
        return bool(variants.get(variant_key))
    
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
    def _get_brand_data(queryset):
        """
        Get brand IDs and brand data in one optimized query
        Returns: (brand_ids_list, brands_dict) where brands_dict maps brand_id -> (name, country)
        """
        brand_ids = queryset.exclude(
            Q(medicine__brand_id__isnull=True) | Q(medicine__brand_id=0)
        ).values_list('medicine__brand_id', flat=True).distinct()
        
        brand_ids_list = list(brand_ids)
        brands_dict = {}
        
        if brand_ids_list:
            # Get all brand data in single query
            brands_data = Brand.objects.using('store').filter(
                id__in=brand_ids_list,
                active=True
            ).values_list('id', 'name', 'country')
            
            brands_dict = {
                brand_id: (name, country)
                for brand_id, name, country in brands_data
            }
        
        return brand_ids_list, brands_dict
    
    @staticmethod
    def _extract_variants(queryset, brand_ids_list, brands_dict):
        """
        Extract variants from queryset with optimized queries
        Returns: dict with countries, brands, priceRanges, priceStats,
                 targetAudiences, flavors, indications
        """
        variants = {
            'countries': set(),
            'brands': [],
            'priceRanges': [],
            'priceStats': {},
            'targetAudiences': set(),
            'flavors': set(),
            'indications': set()
        }
        
        # Extract brands and countries from pre-computed brand data
        brands_list = []
        for brand_id, (brand_name, country) in brands_dict.items():
            if brand_name:
                brands_list.append(brand_name)
            if country:
                variants['countries'].add(country)
        
        variants['brands'] = sorted(brands_list)
        variants['countries'] = sorted(list(variants['countries']))
        
        # Pre-extract text-based filters in single pass with iterator for memory efficiency
        target_audience_counts = defaultdict(int)
        flavor_counts = defaultdict(int)
        indication_counts = defaultdict(int)
        
        # Use iterator to avoid loading all objects into memory
        queryset_with_medicine = queryset.select_related('medicine').iterator(chunk_size=100)
        
        for unit in queryset_with_medicine:
            # Extract targetAudience
            target_audiences = DynamicFiltersService._extract_target_audience(unit)
            for audience in target_audiences:
                target_audience_counts[audience] += 1
                variants['targetAudiences'].add(audience)
            
            # Extract flavor
            flavors = DynamicFiltersService._extract_flavor(unit)
            for flavor in flavors:
                flavor_counts[flavor] += 1
                variants['flavors'].add(flavor)
            
            # Extract indication
            indications = DynamicFiltersService._extract_indication(unit)
            for indication in indications:
                indication_counts[indication] += 1
                variants['indications'].add(indication)
        
        variants['targetAudiences'] = sorted(list(variants['targetAudiences']))
        variants['flavors'] = sorted(list(variants['flavors']))
        variants['indications'] = sorted(list(variants['indications']))
        
        # Store counts for later use in filter building
        variants['_target_audience_counts'] = dict(target_audience_counts)
        variants['_flavor_counts'] = dict(flavor_counts)
        variants['_indication_counts'] = dict(indication_counts)
        
        # Calculate price stats (single query)
        price_stats = queryset.exclude(price_value=0).aggregate(
            min=Min('price_value'),
            max=Max('price_value'),
            avg=Avg('price_value')
        )
        
        if price_stats['min'] is not None:
            # Optimize median calculation: use exact for small datasets, average for large
            price_count = queryset.exclude(price_value=0).count()
            if price_count > 1000:
                # For large datasets, use average as approximation (already computed)
                median = price_stats['avg'] if price_stats['avg'] else 0
            else:
                # Use exact median for small datasets
                all_prices = list(queryset.exclude(price_value=0).values_list('price_value', flat=True))
                median = DynamicFiltersService._calculate_median(all_prices)
            
            variants['priceStats'] = {
                'min': int(price_stats['min']),
                'max': int(price_stats['max']),
                'average': float(price_stats['avg']) if price_stats['avg'] else 0,
                'median': median
            }
            
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
    def _extract_target_audience(medicine_unit):
        """Extract target audience from specifications JSON or usage field"""
        audiences = []
        
        # Try to get from specifications JSON
        if medicine_unit.specifications and isinstance(medicine_unit.specifications, dict):
            for key in SPECIFICATION_KEYS['targetAudience']:
                value = medicine_unit.specifications.get(key)
                if value:
                    if isinstance(value, list):
                        audiences.extend([str(v).strip() for v in value if v])
                    elif isinstance(value, str):
                        audiences.append(value.strip())
        
        # Fallback to usage field
        if not audiences and medicine_unit.medicine and medicine_unit.medicine.usage:
            usage_text = medicine_unit.medicine.usage.lower()
            for audience, keywords in TARGET_AUDIENCE_PATTERNS.items():
                if any(keyword in usage_text for keyword in keywords):
                    audiences.append(audience)
        
        return [a for a in audiences if a]
    
    @staticmethod
    def _extract_flavor(medicine_unit):
        """Extract flavor from specifications JSON"""
        flavors = []
        
        if medicine_unit.specifications and isinstance(medicine_unit.specifications, dict):
            for key in SPECIFICATION_KEYS['flavor']:
                value = medicine_unit.specifications.get(key)
                if value:
                    if isinstance(value, list):
                        flavors.extend([str(v).strip() for v in value if v])
                    elif isinstance(value, str):
                        flavors.append(value.strip())
        
        return [f for f in flavors if f]
    
    @staticmethod
    def _extract_indication(medicine_unit):
        """Extract indication from usage or description field"""
        indications = []
        
        # Check usage field first
        text_to_check = ''
        if medicine_unit.medicine and medicine_unit.medicine.usage:
            text_to_check = medicine_unit.medicine.usage.lower()
        
        # Fallback to description
        if not text_to_check and medicine_unit.medicine and medicine_unit.medicine.description:
            text_to_check = medicine_unit.medicine.description.lower()
        
        if text_to_check:
            for indication, keywords in INDICATION_KEYWORDS.items():
                if any(keyword in text_to_check for keyword in keywords):
                    indications.append(indication)
        
        return indications
    
    @staticmethod
    def _build_filters(queryset, variants, category_slug=None, category=None, brand_ids_list=None, brands_dict=None):
        """
        Build filters structure with optimized queries (no N+1)
        Supports category-specific filter configuration
        """
        # Get category type
        if category:
            category_type = DynamicFiltersService._get_category_type_from_category(category)
        elif category_slug:
            category_type = DynamicFiltersService._get_category_type(category_slug)
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
        for filter_id in filter_priority:
            if filter_id not in enabled_filters:
                continue
            
            if not DynamicFiltersService._has_variants(variants, filter_id):
                continue
            
            filter_obj = DynamicFiltersService._build_single_filter(
                queryset, variants, filter_id, brand_ids_list, brands_dict
            )
            if filter_obj:
                filters.append(filter_obj)
        
        return filters
    
    @staticmethod
    def _build_single_filter(queryset, variants, filter_id, brand_ids_list=None, brands_dict=None):
        """Build a single filter based on filter_id"""
        # Filter: Nước sản xuất (Country) - Only from Brand.country (most reliable)
        if filter_id == 'country' and variants['countries']:
            if not brand_ids_list:
                return None
            
            # Build country count map from Brand.country (optimized)
            # Group brand_ids by country first to reduce queries
            country_to_brand_ids = defaultdict(list)
            for brand_id, (brand_name, country) in brands_dict.items():
                if country:
                    country_to_brand_ids[country].append(brand_id)
            
            # Count products for each country
            country_count_map = {}
            for country, brand_ids_for_country in country_to_brand_ids.items():
                count = queryset.filter(
                    medicine__brand_id__in=brand_ids_for_country
                ).count()
                country_count_map[country] = count
            
            # Build options
            country_options = []
            for country in sorted(variants['countries'])[:FILTER_CONFIGS['country']['limit']]:
                country_options.append({
                    'value': country,
                    'label': country,
                    'count': country_count_map.get(country, 0)
                })
            
            config = FILTER_CONFIGS['country']
            return {
                'id': 'country',
                'type': config['type'],
                'label': config['label'],
                'field': config['field'],
                'searchable': config['searchable'],
                'options': country_options,
                'defaultSelected': [],
                'showMore': len(variants['countries']) > config['limit']
            }
        
        # Filter: Thương hiệu (Brand)
        if filter_id == 'brand' and variants['brands']:
            if not brand_ids_list:
                return None
            
            # Get brand_ids and count products per brand_id for ALL brands (not just top N)
            # This ensures accurate counts for all brands in variants
            brand_id_counts = queryset.exclude(
                Q(medicine__brand_id__isnull=True) | Q(medicine__brand_id=0)
            ).values('medicine__brand_id').annotate(
                count=Count('id')
            )
            
            # Build brand_count_map using pre-computed brands_dict
            brand_count_map = {}
            for item in brand_id_counts:
                brand_id = item['medicine__brand_id']
                brand_name = brands_dict.get(brand_id, (None, None))[0]
                if brand_name:
                    brand_count_map[brand_name] = item['count']
            
            # Build options with counts for all brands, then sort by count descending
            brand_options = []
            for brand_name in variants['brands']:
                count = brand_count_map.get(brand_name, 0)
                if count > 0:  # Only include brands with products
                    brand_options.append({
                        'value': brand_name,
                        'label': brand_name,
                        'count': count
                    })
            
            # Sort by count descending, then by name
            brand_options.sort(key=lambda x: (-x['count'], x['label']))
            
            # Limit to top N brands
            limit = FILTER_CONFIGS['brand']['limit']
            brand_options = brand_options[:limit]
            
            config = FILTER_CONFIGS['brand']
            return {
                'id': 'brand',
                'type': config['type'],
                'label': config['label'],
                'field': config['field'],
                'searchable': config['searchable'],
                'options': brand_options,
                'defaultSelected': [],
                'showMore': len(variants['brands']) > limit
            }
        
        # Filter: Giá bán (Price Range)
        if filter_id == 'priceRange' and variants['priceRanges']:
            price_options = []
            for price_range_key in sorted(variants['priceRanges']):
                count = DynamicFiltersService._count_by_price_range(queryset, price_range_key)
                price_options.append({
                    'value': price_range_key,
                    'label': PRICE_RANGES[price_range_key]['label'],
                    'count': count
                })
            
            config = FILTER_CONFIGS['priceRange']
            return {
                'id': 'priceRange',
                'type': config['type'],
                'label': config['label'],
                'field': config['field'],
                'searchable': config['searchable'],
                'options': price_options,
                'defaultSelected': [],
                'showMore': False
            }
        
        # Filter: Đối tượng sử dụng (Target Audience)
        if filter_id == 'targetAudience' and variants['targetAudiences']:
            # Use pre-computed counts
            counts = variants.get('_target_audience_counts', {})
            target_audience_options = []
            for variant_value in sorted(variants['targetAudiences'])[:FILTER_CONFIGS['targetAudience']['limit']]:
                count = counts.get(variant_value, 0)
                if count > 0:
                    target_audience_options.append({
                        'value': variant_value,
                        'label': variant_value,
                        'count': count
                    })
            
            if target_audience_options:
                config = FILTER_CONFIGS['targetAudience']
                return {
                    'id': 'targetAudience',
                    'type': config['type'],
                    'label': config['label'],
                    'field': config['field'],
                    'searchable': config['searchable'],
                    'options': target_audience_options,
                    'defaultSelected': [],
                    'showMore': len(variants['targetAudiences']) > config['limit']
                }
        
        # Filter: Mùi vị/Mùi hương (Flavor)
        if filter_id == 'flavor' and variants['flavors']:
            # Use pre-computed counts
            counts = variants.get('_flavor_counts', {})
            flavor_options = []
            for variant_value in sorted(variants['flavors'])[:FILTER_CONFIGS['flavor']['limit']]:
                count = counts.get(variant_value, 0)
                if count > 0:
                    flavor_options.append({
                        'value': variant_value,
                        'label': variant_value,
                        'count': count
                    })
            
            if flavor_options:
                config = FILTER_CONFIGS['flavor']
                return {
                    'id': 'flavor',
                    'type': config['type'],
                    'label': config['label'],
                    'field': config['field'],
                    'searchable': config['searchable'],
                    'options': flavor_options,
                    'defaultSelected': [],
                    'showMore': len(variants['flavors']) > config['limit']
                }
        
        # Filter: Chỉ định (Indication)
        if filter_id == 'indication' and variants['indications']:
            # Use pre-computed counts
            counts = variants.get('_indication_counts', {})
            indication_options = []
            for variant_value in sorted(variants['indications'])[:FILTER_CONFIGS['indication']['limit']]:
                count = counts.get(variant_value, 0)
                if count > 0:
                    indication_options.append({
                        'value': variant_value,
                        'label': variant_value,
                        'count': count
                    })
            
            if indication_options:
                config = FILTER_CONFIGS['indication']
                return {
                    'id': 'indication',
                    'type': config['type'],
                    'label': config['label'],
                    'field': config['field'],
                    'searchable': config['searchable'],
                    'options': indication_options,
                    'defaultSelected': [],
                    'showMore': len(variants['indications']) > config['limit']
                }
        
        return None
    
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
        """Invalidate cache for dynamic filters"""
        if category_slug:
            cache_key = f'{CACHE_PREFIX}:{category_slug}'
            cache.delete(cache_key)
            logger.info(f'Invalidated cache for category: {category_slug}')
        else:
            logger.warning('Invalidating all filters cache not implemented')
