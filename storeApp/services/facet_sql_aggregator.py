"""
SQL-backed facet aggregation for dynamic filters (P2a).

Brand/country lists and price stats are computed without scanning variants in Python.
"""
from django.db.models import Avg, Max, Min

from storeApp.services.filter_helpers import FilterHelpers


class FacetSqlAggregator:
    """Build SQL-backed facet variant payloads for dynamic filters."""

    @staticmethod
    def empty_text_variant_keys():
        return {
            "targetAudiences": set(),
            "flavors": set(),
            "indications": set(),
            "skinTypes": set(),
            "medicineTypes": set(),
            "ingredients": set(),
            "_target_audience_counts": {},
            "_flavor_counts": {},
            "_indication_counts": {},
            "_skin_type_counts": {},
            "_medicine_type_counts": {},
            "_ingredient_counts": {},
        }

    @staticmethod
    def build_brand_country_variants(brands_dict):
        brands_list = []
        countries = set()
        for _brand_id, (brand_name, country) in brands_dict.items():
            if brand_name:
                brands_list.append(brand_name)
            if country:
                countries.add(country)

        return {
            "countries": sorted(countries),
            "brands": sorted(brands_list),
        }

    @staticmethod
    def apply_price_facets(queryset, variants):
        price_stats = queryset.exclude(price_value=0).aggregate(
            min=Min("price_value"),
            max=Max("price_value"),
            avg=Avg("price_value"),
        )

        if price_stats["min"] is None:
            variants["priceStats"] = {}
            variants["priceRanges"] = []
            return

        price_count = queryset.exclude(price_value=0).count()
        if price_count > 1000:
            median = price_stats["avg"] if price_stats["avg"] else 0
        else:
            all_prices = list(
                queryset.exclude(price_value=0).values_list("price_value", flat=True)
            )
            median = FilterHelpers.calculate_median(all_prices)

        variants["priceStats"] = {
            "min": int(price_stats["min"]),
            "max": int(price_stats["max"]),
            "average": float(price_stats["avg"]) if price_stats["avg"] else 0,
            "median": median,
        }
        variants["priceRanges"] = FilterHelpers.generate_price_ranges(
            price_stats["min"],
            price_stats["max"],
        )

    @staticmethod
    def build_sql_variants(queryset, brands_dict):
        variants = {
            "priceRanges": [],
            "priceStats": {},
            **FacetSqlAggregator.build_brand_country_variants(brands_dict),
            **FacetSqlAggregator.empty_text_variant_keys(),
        }
        FacetSqlAggregator.apply_price_facets(queryset, variants)
        return variants
