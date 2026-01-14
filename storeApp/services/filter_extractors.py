"""
Filter Extractors
Methods for extracting filter values from product data
"""
import logging
from collections import defaultdict
from django.db.models import Min, Max, Avg
from storeApp.services.filter_constants import (
    TARGET_AUDIENCE_PATTERNS,
    INDICATION_KEYWORDS,
    SPECIFICATION_KEYS,
    SKIN_TYPE_PATTERNS,
    MEDICINE_TYPE_PATTERNS,
    INGREDIENT_KEYWORDS
)
from storeApp.services.filter_helpers import FilterHelpers

logger = logging.getLogger(__name__)


class FilterExtractors:
    """Extractors for dynamic filter values"""
    
    @staticmethod
    def extract_variants(queryset, brand_ids_list, brands_dict):
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
            'indications': set(),
            'skinTypes': set(),
            'medicineTypes': set(),
            'ingredients': set()
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
        skin_type_counts = defaultdict(int)
        medicine_type_counts = defaultdict(int)
        ingredient_counts = defaultdict(int)
        
        # Use iterator to avoid loading all objects into memory
        queryset_with_medicine = queryset.select_related('medicine').iterator(chunk_size=100)
        
        for unit in queryset_with_medicine:
            # Extract targetAudience
            target_audiences = FilterExtractors.extract_target_audience(unit)
            for audience in target_audiences:
                target_audience_counts[audience] += 1
                variants['targetAudiences'].add(audience)
            
            # Extract flavor
            flavors = FilterExtractors.extract_flavor(unit)
            for flavor in flavors:
                flavor_counts[flavor] += 1
                variants['flavors'].add(flavor)
            
            # Extract indication
            indications = FilterExtractors.extract_indication(unit)
            for indication in indications:
                indication_counts[indication] += 1
                variants['indications'].add(indication)
            
            # Extract skinType (for cosmetics)
            skin_types = FilterExtractors.extract_skin_type(unit)
            for skin_type in skin_types:
                skin_type_counts[skin_type] += 1
                variants['skinTypes'].add(skin_type)
            
            # Extract medicineType (for medicine)
            medicine_types = FilterExtractors.extract_medicine_type(unit)
            for medicine_type in medicine_types:
                medicine_type_counts[medicine_type] += 1
                variants['medicineTypes'].add(medicine_type)
            
            # Extract ingredients (for medicine)
            ingredients = FilterExtractors.extract_ingredients(unit)
            for ingredient in ingredients:
                ingredient_counts[ingredient] += 1
                variants['ingredients'].add(ingredient)
        
        variants['targetAudiences'] = sorted(list(variants['targetAudiences']))
        variants['flavors'] = sorted(list(variants['flavors']))
        variants['indications'] = sorted(list(variants['indications']))
        variants['skinTypes'] = sorted(list(variants['skinTypes']))
        variants['medicineTypes'] = sorted(list(variants['medicineTypes']))
        variants['ingredients'] = sorted(list(variants['ingredients']))
        
        # Store counts for later use in filter building
        variants['_target_audience_counts'] = dict(target_audience_counts)
        variants['_flavor_counts'] = dict(flavor_counts)
        variants['_indication_counts'] = dict(indication_counts)
        variants['_skin_type_counts'] = dict(skin_type_counts)
        variants['_medicine_type_counts'] = dict(medicine_type_counts)
        variants['_ingredient_counts'] = dict(ingredient_counts)
        
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
                median = FilterHelpers.calculate_median(all_prices)
            
            variants['priceStats'] = {
                'min': int(price_stats['min']),
                'max': int(price_stats['max']),
                'average': float(price_stats['avg']) if price_stats['avg'] else 0,
                'median': median
            }
            
            variants['priceRanges'] = FilterHelpers.generate_price_ranges(
                price_stats['min'],
                price_stats['max']
            )
        
        return variants
    
    @staticmethod
    def extract_from_specifications(medicine_unit, filter_id, split_string=False):
        """
        Generic method to extract values from specifications JSON
        
        Args:
            medicine_unit: MedicineUnit instance
            filter_id: Filter ID to get specification keys
            split_string: If True, split string values by comma/semicolon
        
        Returns:
            list: Extracted values
        """
        values = []
        
        if not medicine_unit.specifications or not isinstance(medicine_unit.specifications, dict):
            return values
        
        spec_keys = SPECIFICATION_KEYS.get(filter_id, [])
        for key in spec_keys:
            value = medicine_unit.specifications.get(key)
            if value:
                if isinstance(value, list):
                    values.extend([str(v).strip() for v in value if v])
                elif isinstance(value, str):
                    if split_string:
                        # Split by comma or semicolon (for ingredients)
                        values.extend([i.strip() for i in value.replace(';', ',').split(',') if i.strip()])
                    else:
                        values.append(value.strip())
        
        return [v for v in values if v]
    
    @staticmethod
    def extract_from_text_patterns(medicine_unit, patterns_dict, text_fields=None):
        """
        Generic method to extract values from text fields using pattern matching
        
        Args:
            medicine_unit: MedicineUnit instance
            patterns_dict: Dictionary mapping value -> list of keywords
            text_fields: List of field names to check (default: ['usage', 'description'])
        
        Returns:
            list: Matched values
        """
        if text_fields is None:
            text_fields = ['usage', 'description']
        
        values = []
        text_to_check = ''
        
        if not medicine_unit.medicine:
            return values
        
        # Check fields in order
        for field_name in text_fields:
            field_value = getattr(medicine_unit.medicine, field_name, None)
            if field_value:
                text_to_check = str(field_value).lower()
                break
        
        if not text_to_check:
            return values
        
        # Match against patterns
        for value, keywords in patterns_dict.items():
            if any(keyword in text_to_check for keyword in keywords):
                values.append(value)
        
        return values
    
    @staticmethod
    def extract_target_audience(medicine_unit):
        """Extract target audience from specifications JSON or usage field"""
        # Try specifications first
        audiences = FilterExtractors.extract_from_specifications(
            medicine_unit, 'targetAudience'
        )
        
        # Fallback to usage field with pattern matching
        if not audiences:
            audiences = FilterExtractors.extract_from_text_patterns(
                medicine_unit, TARGET_AUDIENCE_PATTERNS, ['usage']
            )
        
        return audiences
    
    @staticmethod
    def extract_flavor(medicine_unit):
        """Extract flavor from specifications JSON"""
        return FilterExtractors.extract_from_specifications(
            medicine_unit, 'flavor'
        )
    
    @staticmethod
    def extract_indication(medicine_unit):
        """Extract indication from usage or description field"""
        return FilterExtractors.extract_from_text_patterns(
            medicine_unit, INDICATION_KEYWORDS, ['usage', 'description']
        )
    
    @staticmethod
    def extract_skin_type(medicine_unit):
        """Extract skin type from specifications or description"""
        # Try specifications first
        skin_types = FilterExtractors.extract_from_specifications(
            medicine_unit, 'skinType'
        )
        
        # Fallback to description with pattern matching
        if not skin_types:
            skin_types = FilterExtractors.extract_from_text_patterns(
                medicine_unit, SKIN_TYPE_PATTERNS, ['description']
            )
        
        return skin_types
    
    @staticmethod
    def extract_medicine_type(medicine_unit):
        """Extract medicine type from usage or description"""
        return FilterExtractors.extract_from_text_patterns(
            medicine_unit, MEDICINE_TYPE_PATTERNS, ['usage', 'description']
        )
    
    @staticmethod
    def extract_ingredients(medicine_unit):
        """Extract ingredients from specifications or description"""
        # Try specifications first (with string splitting)
        ingredients = FilterExtractors.extract_from_specifications(
            medicine_unit, 'ingredients', split_string=True
        )
        
        # Fallback to description (extract known ingredients)
        if not ingredients and medicine_unit.medicine and medicine_unit.medicine.description:
            text = medicine_unit.medicine.description.lower()
            for ingredient in INGREDIENT_KEYWORDS:
                if ingredient.lower() in text:
                    ingredients.append(ingredient.title())
        
        return ingredients
