from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import models
from mainApp.models import MedicineUnit, Category, Medicine
from storeApp.serializers import ProductSerializer
from storeApp.filters import ProductFilter
from storeApp.viewsets.product import ProductPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters


@api_view(['GET'])
@permission_classes([AllowAny])
def products_by_category_slug(request, category_slug):
    """
    Xử lý 3 trường hợp:
    1. {category_slug} - Lấy danh sách sản phẩm theo category slug
    2. {category_slug}/{subcategory_slug}/... - Lấy danh sách sản phẩm theo nested category path
    3. {category_slug}/{subcategory_slug}/.../{medicine_slug} - Lấy chi tiết sản phẩm theo medicine slug
    """
    category_slug = category_slug.rstrip('/')
    
    if '/' in category_slug:
        parts = category_slug.split('/')
        medicine_slug = parts[-1]
        cat_path_slug = '/'.join(parts[:-1])
        
        medicine = Medicine.objects.using('default').filter(active=True).filter(
            slug__iexact=medicine_slug
        ).first()
        
        if medicine:
            category = Category.objects.using('default').filter(active=True).filter(
                models.Q(path_slug__iexact=cat_path_slug) | 
                models.Q(slug__iexact=cat_path_slug)
            ).first()
            
            if category:
                product = MedicineUnit.objects.using('default').filter(
                    active=True,
                    category=category,
                    medicine=medicine
                ).select_related('medicine', 'category').first()
                
                if product:
                    serializer = ProductSerializer(product)
                    return Response(serializer.data)
                else:
                    return Response(
                        {'detail': f'Không tìm thấy sản phẩm với category: {cat_path_slug} và medicine: {medicine_slug}'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                return Response(
                    {'detail': f'Không tìm thấy danh mục với path: {cat_path_slug} cho medicine: {medicine_slug}'},
                    status=status.HTTP_404_NOT_FOUND
                )
    
    try:
        category = Category.objects.using('default').filter(active=True).filter(
            models.Q(path_slug__iexact=category_slug) | 
            models.Q(slug__iexact=category_slug)
        ).first()
        
        if not category:
            return Response(
                {'detail': f'Không tìm thấy danh mục hoặc sản phẩm với slug: {category_slug}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        category_path_slug = category.path_slug or category.slug
        
        category_ids = [category.id]
        
        subcategories = Category.objects.using('default').filter(
            active=True,
            path_slug__istartswith=f"{category_path_slug}/"
        ).values_list('id', flat=True)
        
        category_ids.extend(list(subcategories))
        
        queryset = MedicineUnit.objects.using('default').filter(
            active=True, 
            category_id__in=category_ids
        ).select_related('medicine', 'category')
        
    except Exception as e:
        return Response(
            {'detail': f'Lỗi khi tìm kiếm danh mục với slug: {category_slug}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    filter_backend = DjangoFilterBackend()
    queryset = filter_backend.filter_queryset(request, queryset, ProductFilter)
    
    search_backend = filters.SearchFilter()
    search_backend.search_fields = ['medicine__name', 'package_size', 'medicine__web_name']
    queryset = search_backend.filter_queryset(request, queryset, None)
    
    ordering_backend = filters.OrderingFilter()
    ordering_backend.ordering_fields = ['price_value', 'created_date', 'in_stock', 'product_ranking']
    ordering_backend.ordering = ['-created_date']
    queryset = ordering_backend.filter_queryset(request, queryset, None)
    
    paginator = ProductPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        serializer = ProductSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    serializer = ProductSerializer(queryset, many=True)
    return Response(serializer.data)
