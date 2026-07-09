"""
Filter Extractors
Methods for extracting filter values from product data
"""
from collections import defaultdict

from storeApp.services.facet_sql_aggregator import FacetSqlAggregator
from storeApp.services.filter_constants import (
    TARGET_AUDIENCE_PATTERNS,
    INDICATION_KEYWORDS,
    SPECIFICATION_KEYS,
    SKIN_TYPE_PATTERNS,
    MEDICINE_TYPE_PATTERNS,
    INGREDIENT_KEYWORDS,
)
from storeApp.services.filter_helpers import FilterHelpers


TEXT_FILTER_SPECS = {
    "targetAudience": (
        "targetAudiences",
        "_target_audience_counts",
        "extract_target_audience",
    ),
    "flavor": ("flavors", "_flavor_counts", "extract_flavor"),
    "indication": ("indications", "_indication_counts", "extract_indication"),
    "skinType": ("skinTypes", "_skin_type_counts", "extract_skin_type"),
    "medicineType": (
        "medicineTypes",
        "_medicine_type_counts",
        "extract_medicine_type",
    ),
    "ingredients": ("ingredients", "_ingredient_counts", "extract_ingredients"),
}


class FilterExtractors:
    """Extractors for dynamic filter values"""

    @staticmethod
    def _enabled_text_filters(enabled_filters):
        if enabled_filters is None:
            return list(TEXT_FILTER_SPECS.keys())
        return [f for f in enabled_filters if f in TEXT_FILTER_SPECS]

    @staticmethod
    def extract_variants(
        queryset, brand_ids_list, brands_dict, enabled_filters=None
    ):
        """
        Extract variants from queryset.

        SQL path: brand/country/price (no Python iterator).
        Iterator path: text facets only when enabled for the category type.
        """
        _ = brand_ids_list  # retained for callers; brand data comes from brands_dict
        variants = FacetSqlAggregator.build_sql_variants(queryset, brands_dict)

        text_filters = FilterExtractors._enabled_text_filters(enabled_filters)
        if not text_filters:
            FilterExtractors._finalize_text_variants(variants)
            return variants

        FilterExtractors._extract_text_facets(queryset, variants, text_filters)
        FilterExtractors._finalize_text_variants(variants)
        return variants

    @staticmethod
    def _extract_text_facets(queryset, variants, text_filters):
        count_maps = {
            spec[1]: defaultdict(set) for spec in TEXT_FILTER_SPECS.values()
        }

        queryset_with_product = queryset.select_related("product").iterator(
            chunk_size=100
        )
        for variant in queryset_with_product:
            product_id = variant.product_id
            for filter_id in text_filters:
                variant_key, count_key, method_name = TEXT_FILTER_SPECS[filter_id]
                extractor = getattr(FilterExtractors, method_name)
                for value in extractor(variant):
                    count_maps[count_key][value].add(product_id)
                    variants[variant_key].add(value)

        for _filter_id, (variant_key, count_key, _method_name) in TEXT_FILTER_SPECS.items():
            variants[count_key] = {
                key: len(product_ids)
                for key, product_ids in count_maps[count_key].items()
            }
            if _filter_id not in text_filters:
                variants[variant_key] = set()
                variants[count_key] = {}

    @staticmethod
    def _finalize_text_variants(variants):
        for variant_key, _count_key, _method_name in TEXT_FILTER_SPECS.values():
            if isinstance(variants.get(variant_key), set):
                variants[variant_key] = sorted(variants[variant_key])

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

        product = getattr(medicine_unit, "product", None)
        specs = getattr(product, "specifications", None) if product else None
        if not specs or not isinstance(specs, dict):
            return values

        spec_keys = SPECIFICATION_KEYS.get(filter_id, [])
        for key in spec_keys:
            value = specs.get(key)
            if value:
                if isinstance(value, list):
                    values.extend([str(v).strip() for v in value if v])
                elif isinstance(value, str):
                    if split_string:
                        values.extend(
                            [
                                i.strip()
                                for i in value.replace(";", ",").split(",")
                                if i.strip()
                            ]
                        )
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
            text_fields = ["usage", "description"]

        values = []
        text_to_check = ""

        product = getattr(medicine_unit, "product", None)
        if not product:
            return values

        for field_name in text_fields:
            field_value = getattr(product, field_name, None)
            if field_value:
                text_to_check = str(field_value).lower()
                break

        if not text_to_check:
            return values

        for value, keywords in patterns_dict.items():
            if any(keyword in text_to_check for keyword in keywords):
                values.append(value)

        return values

    @staticmethod
    def extract_target_audience(medicine_unit):
        """Extract target audience from specifications JSON or usage field"""
        audiences = FilterExtractors.extract_from_specifications(
            medicine_unit, "targetAudience"
        )

        if not audiences:
            audiences = FilterExtractors.extract_from_text_patterns(
                medicine_unit, TARGET_AUDIENCE_PATTERNS, ["usage"]
            )

        return audiences

    @staticmethod
    def extract_flavor(medicine_unit):
        """Extract flavor from specifications JSON"""
        return FilterExtractors.extract_from_specifications(medicine_unit, "flavor")

    @staticmethod
    def extract_indication(medicine_unit):
        """Extract indication from usage or description field"""
        return FilterExtractors.extract_from_text_patterns(
            medicine_unit, INDICATION_KEYWORDS, ["usage", "description"]
        )

    @staticmethod
    def extract_skin_type(medicine_unit):
        """Extract skin type from specifications or description"""
        skin_types = FilterExtractors.extract_from_specifications(
            medicine_unit, "skinType"
        )

        if not skin_types:
            skin_types = FilterExtractors.extract_from_text_patterns(
                medicine_unit, SKIN_TYPE_PATTERNS, ["description"]
            )

        return skin_types

    @staticmethod
    def extract_medicine_type(medicine_unit):
        """Extract medicine type from usage or description"""
        return FilterExtractors.extract_from_text_patterns(
            medicine_unit, MEDICINE_TYPE_PATTERNS, ["usage", "description"]
        )

    @staticmethod
    def extract_ingredients(medicine_unit):
        """Extract ingredients from specifications or description"""
        ingredients = FilterExtractors.extract_from_specifications(
            medicine_unit, "ingredients", split_string=True
        )

        product = getattr(medicine_unit, "product", None)
        if not ingredients and product and getattr(product, "description", None):
            text = product.description.lower()
            for ingredient in INGREDIENT_KEYWORDS:
                if ingredient.lower() in text:
                    ingredients.append(ingredient.title())

        return ingredients
