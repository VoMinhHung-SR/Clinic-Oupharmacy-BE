import django_filters
from django.db import models
from django.db.models import Exists, OuterRef

from storeApp.models import ProductCategory, ProductVariant


class ProductFilter(django_filters.FilterSet):
    """Filter cho products API trong store"""

    kw = django_filters.CharFilter(field_name="product__name", lookup_expr="icontains")
    category = django_filters.NumberFilter(method="filter_category")
    category_slug = django_filters.CharFilter(
        method="filter_category_slug", help_text="Filter by category slug or path_slug"
    )
    brand = django_filters.NumberFilter(field_name="product__brand__id")
    min_price = django_filters.NumberFilter(field_name="price_value", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price_value", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    price_sort = django_filters.CharFilter(method="filter_price_sort")
    is_hot = django_filters.BooleanFilter(field_name="is_hot")

    class Meta:
        model = ProductVariant
        fields = [
            "kw",
            "category",
            "category_slug",
            "brand",
            "min_price",
            "max_price",
            "in_stock",
            "price_sort",
            "is_hot",
        ]

    def filter_category(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(
            Exists(
                ProductCategory.objects.using(queryset.db).filter(
                    product_id=OuterRef("product_id"),
                    category_id=value,
                )
            )
        )

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

        return queryset.filter(
            Exists(
                ProductCategory.objects.using(queryset.db)
                .filter(product_id=OuterRef("product_id"))
                .filter(
                    models.Q(category__path_slug__iexact=value)
                    | models.Q(category__slug__iexact=value)
                )
            )
        )
