from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import models
from mainApp.models import MedicineUnit, Category
from storeApp.serializers import ProductSerializer
from storeApp.filters import ProductFilter
from storeApp.viewsets.product import ProductPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters


@api_view(['GET'])
@permission_classes([AllowAny])
def products_by_category_slug(request, category_slug):
    """
    Lấy danh sách sản phẩm theo category slug từ URL path.
    Ví dụ: /api/store/thuc-pham-chuc-nang/vitamin-khoang-chat
    """
    # Tìm category theo path_slug hoặc slug (case-insensitive)
    try:
        category = Category.objects.using('default').filter(active=True).get(
            models.Q(path_slug__iexact=category_slug) | 
            models.Q(slug__iexact=category_slug)
        )
    except Category.DoesNotExist:
        return Response(
            {'detail': f'Không tìm thấy danh mục với slug: {category_slug}'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Lấy queryset và filter theo category
    queryset = MedicineUnit.objects.using('default').filter(
        active=True, 
        category=category
    ).select_related('medicine', 'category')
    
    # Áp dụng các filter từ query params
    filter_backend = DjangoFilterBackend()
    queryset = filter_backend.filter_queryset(request, queryset, ProductFilter)
    
    # Áp dụng search filter nếu có
    search_backend = filters.SearchFilter()
    search_backend.search_fields = ['medicine__name', 'package_size', 'medicine__web_name']
    queryset = search_backend.filter_queryset(request, queryset, None)
    
    # Áp dụng ordering
    ordering_backend = filters.OrderingFilter()
    ordering_backend.ordering_fields = ['price_value', 'created_date', 'in_stock', 'product_ranking']
    ordering_backend.ordering = ['-created_date']
    queryset = ordering_backend.filter_queryset(request, queryset, None)
    
    # Pagination
    paginator = ProductPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        serializer = ProductSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    serializer = ProductSerializer(queryset, many=True)
    return Response(serializer.data)
