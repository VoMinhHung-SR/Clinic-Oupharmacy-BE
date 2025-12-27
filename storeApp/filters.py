import django_filters
from django.db import models
from mainApp.models import MedicineUnit


class ProductFilter(django_filters.FilterSet):
    """Filter cho products API trong store"""
    kw = django_filters.CharFilter(field_name="medicine__name", lookup_expr="icontains")
    category = django_filters.NumberFilter(field_name="category__id")
    category_slug = django_filters.CharFilter(method="filter_category_slug", help_text="Filter by category slug or path_slug")
    brand = django_filters.NumberFilter(field_name="medicine__brand_id")
    min_price = django_filters.NumberFilter(field_name="price_value", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price_value", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    price_sort = django_filters.CharFilter(method="filter_price_sort")
    
    class Meta:
        model = MedicineUnit
        fields = ['kw', 'category', 'category_slug', 'brand', 'min_price', 'max_price', 'in_stock', 'price_sort']
    
    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(in_stock__gt=0)
        return queryset
    
    def filter_price_sort(self, queryset, name, value):
        if value == "asc":
            return queryset.order_by("price_value")
        elif value == "desc":
            return queryset.order_by("-price_value")
        return queryset
    
    def filter_category_slug(self, queryset, name, value):
        if not value:
            return queryset
        
        # Try to match by path_slug first (full path), then by slug
        return queryset.filter(
            models.Q(category__path_slug__iexact=value) | 
            models.Q(category__slug__iexact=value)
        )

