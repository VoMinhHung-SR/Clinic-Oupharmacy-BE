import django_filters
from mainApp.models import MedicineUnit


class ProductFilter(django_filters.FilterSet):
    """Filter cho products API trong store"""
    kw = django_filters.CharFilter(field_name="medicine__name", lookup_expr="icontains")
    category = django_filters.NumberFilter(field_name="category__id")
    brand = django_filters.NumberFilter(field_name="brand_id")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    price_sort = django_filters.CharFilter(method="filter_price_sort")
    
    class Meta:
        model = MedicineUnit
        fields = ['kw', 'category', 'brand', 'min_price', 'max_price', 'in_stock', 'price_sort']
    
    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(in_stock__gt=0)
        return queryset
    
    def filter_price_sort(self, queryset, name, value):
        if value == "asc":
            return queryset.order_by("price")
        elif value == "desc":
            return queryset.order_by("-price")
        return queryset

