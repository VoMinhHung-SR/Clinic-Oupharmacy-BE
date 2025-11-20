from rest_framework import viewsets, generics, filters
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from mainApp.models import MedicineUnit
from storeApp.serializers import ProductSerializer
from storeApp.filters import ProductFilter
from rest_framework.pagination import PageNumberPagination


class ProductPagination(PageNumberPagination):
    """Pagination cho products API"""
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProductViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView):
    serializer_class = ProductSerializer
    pagination_class = ProductPagination
    parser_classes = [JSONParser]
    permission_classes = [AllowAny]
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ProductFilter
    search_fields = ['medicine__name', 'packaging']
    ordering_fields = ['price', 'created_date', 'in_stock']
    ordering = ['-created_date']
    
    def get_queryset(self):
        queryset = MedicineUnit.objects.using('default').filter(active=True).select_related('medicine', 'category')
        
        in_stock_param = self.request.query_params.get('in_stock')
        if in_stock_param is not None:
            if in_stock_param.lower() in ['true', '1']:
                queryset = queryset.filter(in_stock__gt=0)
        
        return queryset.order_by('-created_date')

