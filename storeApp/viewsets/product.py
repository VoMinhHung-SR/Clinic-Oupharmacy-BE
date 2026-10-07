from django.conf import settings
from rest_framework import viewsets, generics, filters
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from storeApp.models import ProductVariant
from storeApp.serializers import ProductVariantSerializer
from storeApp.filters import ProductFilter
from rest_framework.pagination import PageNumberPagination
from django.db.models import OuterRef, Subquery, DecimalField, CharField, Value
from django.db.models.functions import Coalesce
from rest_framework.decorators import action
from rest_framework.response import Response
from storeApp.models import ProductVariantUnit, Product, ProductCategory
from django.db.models import Prefetch


def annotate_variant_unit_price(queryset, db_alias=None):
    """
    Annotate ProductVariant with default/first published unit price fields.

    - price_value: numeric sale/list price (ordering, price_range)
    - list_price_display: unit.price_display (CONSULT vs listed VND)
    """
    alias = db_alias or "default"
    decimal_price = DecimalField(max_digits=12, decimal_places=2)
    default_units = ProductVariantUnit.objects.using(alias).filter(
        variant_id=OuterRef("pk"),
        is_default=True,
        is_published=True,
    )
    fallback_units = (
        ProductVariantUnit.objects.using(alias)
        .filter(
            variant_id=OuterRef("pk"),
            is_published=True,
        )
        .order_by("unit_order", "id")
    )
    return queryset.annotate(
        price_value=Coalesce(
            Subquery(default_units.values("price_value")[:1], output_field=decimal_price),
            Subquery(fallback_units.values("price_value")[:1], output_field=decimal_price),
            Value(0),
            output_field=decimal_price,
        ),
        list_price_display=Coalesce(
            Subquery(
                default_units.values("price_display")[:1],
                output_field=CharField(),
            ),
            Subquery(
                fallback_units.values("price_display")[:1],
                output_field=CharField(),
            ),
            Value(""),
            output_field=CharField(),
        ),
    )


class ProductPagination(PageNumberPagination):
    """Pagination cho products API"""
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


class SitemapFeedPagination(PageNumberPagination):
    """Large pages for storefront sitemap product URLs (lightweight rows)."""

    page_size = 500
    page_size_query_param = "page_size"
    max_page_size = 2000


class ProductViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView):
    serializer_class = ProductVariantSerializer
    pagination_class = ProductPagination
    parser_classes = [JSONParser]
    permission_classes = [AllowAny]
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ProductFilter
    search_fields = ['product__name', 'packing', 'product__web_name', 'sku', 'product__mid']
    ordering_fields = ['price_value', 'created_date', 'in_stock', 'product_ranking']
    ordering = ['-created_date']

    def get_queryset(self):
        store_db_alias = "store" if "store" in settings.DATABASES else "default"
        queryset = annotate_variant_unit_price(
            ProductVariant.objects.using(store_db_alias)
            .filter(active=True)
            .select_related("product__category", "product__brand")
            .prefetch_related(
                Prefetch(
                    "product__product_categories",
                    queryset=ProductCategory.objects.using(store_db_alias).select_related("category"),
                ),
                Prefetch(
                    "units",
                    queryset=ProductVariantUnit.objects.using(store_db_alias).filter(is_published=True).order_by("unit_order", "id"),
                    to_attr="prefetched_units",
                ),
            ),
            db_alias=store_db_alias,
        )
        
        in_stock_param = self.request.query_params.get('in_stock')
        if in_stock_param is not None:
            if in_stock_param.lower() in ['true', '1']:
                queryset = queryset.filter(in_stock__gt=0)
        
        return queryset.order_by('-created_date')

    @action(methods=['get'], detail=False, url_path='summary-counts')
    def summary_counts(self, request):
        products_count = Product.objects.filter(active=True).count()
        variants_count = ProductVariant.objects.filter(active=True).count()
        units_count = ProductVariantUnit.objects.count()
        return Response(
            {
                "products": products_count,
                "variants": variants_count,
                "variant_units": units_count,
            }
        )

    @action(methods=["get"], detail=False, url_path="sitemap")
    def sitemap(self, request):
        """
        Lightweight product URL feed for storefront sitemap.xml.
        Returns path (= category path_slug + product slug), no heavy serializers.
        """
        store_db_alias = "store" if "store" in settings.DATABASES else "default"
        qs = (
            Product.objects.using(store_db_alias)
            .filter(active=True)
            .exclude(slug__isnull=True)
            .exclude(slug="")
            .select_related("category")
            .order_by("id")
            .values("slug", "updated_date", "category__path_slug", "category__slug")
        )
        paginator = SitemapFeedPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        results = []
        for row in page or []:
            slug = (row.get("slug") or "").strip()
            if not slug:
                continue
            cat = (row.get("category__path_slug") or row.get("category__slug") or "").strip()
            path = f"{cat}/{slug}" if cat else slug
            updated = row.get("updated_date")
            results.append(
                {
                    "slug": slug,
                    "path": path,
                    "updated_at": updated.isoformat() if updated else None,
                }
            )
        return paginator.get_paginated_response(results)