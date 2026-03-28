from rest_framework import viewsets, generics, filters
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from storeApp.models import ProductVariant
from storeApp.serializers import ProductVariantSerializer
from storeApp.filters import ProductFilter
from rest_framework.pagination import PageNumberPagination
from django.db.models import OuterRef, Subquery, DecimalField, Value
from django.db.models.functions import Coalesce
from rest_framework.decorators import action
from rest_framework.response import Response
from storeApp.models import ProductVariantUnit, Product


class ProductPagination(PageNumberPagination):
    """Pagination cho products API"""
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProductViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView):
    serializer_class = ProductVariantSerializer
    pagination_class = ProductPagination
    parser_classes = [JSONParser]
    permission_classes = [AllowAny]
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ProductFilter
    search_fields = ['product__name', 'packing', 'product__web_name']
    ordering_fields = ['price_value', 'created_date', 'in_stock', 'product_ranking']
    ordering = ['-created_date']
    
    def get_queryset(self):
        default_unit_price = ProductVariantUnit.objects.filter(
            variant_id=OuterRef('pk'),
            is_default=True,
            is_published=True,
        ).values('price_value')[:1]
        fallback_unit_price = ProductVariantUnit.objects.filter(
            variant_id=OuterRef('pk'),
            is_published=True,
        ).order_by('unit_order', 'id').values('price_value')[:1]
        queryset = ProductVariant.objects.filter(active=True).select_related("product__category", "product__brand").annotate(
            price_value=Coalesce(
                Subquery(default_unit_price, output_field=DecimalField(max_digits=12, decimal_places=2)),
                Subquery(fallback_unit_price, output_field=DecimalField(max_digits=12, decimal_places=2)),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
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