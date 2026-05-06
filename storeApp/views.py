from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db import models
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.db.models import Prefetch
from django.db.models.functions import Lower
from django.utils import timezone
from storeApp.models import ProductVariant, ProductVariantUnit, Category, Product
from storeApp.serializers import ProductVariantSerializer
from storeApp.filters import ProductFilter
from storeApp.viewsets.product import ProductPagination, annotate_variant_unit_price
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from storeApp.services.filter_helpers import FilterHelpers
from storeApp.services.filter_constants import LARGE_CATEGORY_THRESHOLD
from storeApp.models import Notification
from storeApp.serializers import ContactSupportRequestSerializer

STORE_DB_ALIAS = 'store' if 'store' in settings.DATABASES else 'default'
PRICE_RANGE_BUCKETS = [
    ("under_100k", None, 100000),
    ("100k_300k", 100000, 300000),
    ("300k_500k", 300000, 500000),
    ("over_500k", 500000, None),
]


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_bool(value):
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _apply_price_range_filter(queryset, price_range):
    if price_range == "under_100k":
        return queryset.filter(price_value__lt=100000)
    if price_range == "100k_300k":
        return queryset.filter(price_value__gte=100000, price_value__lt=300000)
    if price_range == "300k_500k":
        return queryset.filter(price_value__gte=300000, price_value__lt=500000)
    if price_range == "over_500k":
        return queryset.filter(price_value__gte=500000)
    return queryset


def _build_scalar_facets(queryset):
    price_q = {
        "under_100k": Q(price_value__lt=100000),
        "100k_300k": Q(price_value__gte=100000, price_value__lt=300000),
        "300k_500k": Q(price_value__gte=300000, price_value__lt=500000),
        "over_500k": Q(price_value__gte=500000),
    }
    aggregated = queryset.aggregate(
        under_100k=Count("id", filter=price_q["under_100k"]),
        range_100k_300k=Count("id", filter=price_q["100k_300k"]),
        range_300k_500k=Count("id", filter=price_q["300k_500k"]),
        over_500k=Count("id", filter=price_q["over_500k"]),
        in_stock_count=Count("id", filter=Q(in_stock__gt=0)),
        out_of_stock_count=Count("id", filter=Q(in_stock__lte=0)),
    )
    return {
        "price_ranges": [
            {"key": "under_100k", "count": aggregated["under_100k"]},
            {"key": "100k_300k", "count": aggregated["range_100k_300k"]},
            {"key": "300k_500k", "count": aggregated["range_300k_500k"]},
            {"key": "over_500k", "count": aggregated["over_500k"]},
        ],
        "in_stock": [
            {"key": True, "count": aggregated["in_stock_count"]},
            {"key": False, "count": aggregated["out_of_stock_count"]},
        ],
    }


def _build_facets(queryset):
    category_facets = (
        queryset.values("product__category_id", "product__category__name", "product__category__slug")
        .annotate(count=Count("id"))
        .order_by("-count", "product__category__name")
    )
    brand_facets = (
        queryset.values("product__brand_id", "product__brand__name")
        .annotate(count=Count("id"))
        .order_by("-count", "product__brand__name")
    )

    scalar_facets = _build_scalar_facets(queryset)

    return {
        "category": [
            {
                "id": item["product__category_id"],
                "name": item["product__category__name"],
                "slug": item["product__category__slug"],
                "count": item["count"],
            }
            for item in category_facets
            if item["product__category_id"] is not None
        ],
        "brand": [
            {
                "id": item["product__brand_id"],
                "name": item["product__brand__name"],
                "count": item["count"],
            }
            for item in brand_facets
            if item["product__brand_id"] is not None
        ],
        "price_ranges": scalar_facets["price_ranges"],
        "in_stock": scalar_facets["in_stock"],
    }


@api_view(['GET'])
@permission_classes([AllowAny])
def search_products(request):
    started_at = timezone.now()
    raw_query = (request.query_params.get("q", "") or "").strip()
    page = max(1, _safe_int(request.query_params.get("page"), 1))
    page_size = min(100, max(1, _safe_int(request.query_params.get("page_size"), 12)))
    category = request.query_params.get("category")
    brand = request.query_params.get("brand")
    price_range = request.query_params.get("price_range")
    in_stock = _parse_bool(request.query_params.get("in_stock"))
    sort = request.query_params.get("sort", "relevance")

    queryset = annotate_variant_unit_price(
        ProductVariant.objects.using(STORE_DB_ALIAS)
        .filter(active=True, is_published=True, product__active=True)
        .select_related("product", "product__category", "product__brand"),
        db_alias=STORE_DB_ALIAS,
    ).prefetch_related(
        Prefetch(
            "units",
            queryset=ProductVariantUnit.objects.using(STORE_DB_ALIAS).filter(is_published=True).order_by("unit_order", "id"),
            to_attr="prefetched_units",
        )
    )

    query_normalized = " ".join(raw_query.split())
    query_lookup = query_normalized.casefold()
    if query_lookup:
        queryset = queryset.annotate(
            product_name_lookup=Lower("product__name"),
            web_name_lookup=Lower("product__web_name"),
            category_name_lookup=Lower("product__category__name"),
            brand_name_lookup=Lower("product__brand__name"),
            relevance_score=Case(
                When(product_name_lookup=query_lookup, then=Value(100)),
                When(web_name_lookup=query_lookup, then=Value(95)),
                When(product_name_lookup__startswith=query_lookup, then=Value(80)),
                When(web_name_lookup__startswith=query_lookup, then=Value(75)),
                When(product_name_lookup__contains=query_lookup, then=Value(60)),
                When(web_name_lookup__contains=query_lookup, then=Value(55)),
                When(category_name_lookup__contains=query_lookup, then=Value(35)),
                When(brand_name_lookup__contains=query_lookup, then=Value(30)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        ).filter(
            Q(product_name_lookup__contains=query_lookup)
            | Q(web_name_lookup__contains=query_lookup)
            | Q(category_name_lookup__contains=query_lookup)
            | Q(brand_name_lookup__contains=query_lookup)
        )
    else:
        queryset = queryset.annotate(relevance_score=Value(0, output_field=IntegerField()))

    if category:
        queryset = queryset.filter(product__category_id=category)
    if brand:
        queryset = queryset.filter(product__brand_id=brand)
    if in_stock is True:
        queryset = queryset.filter(in_stock__gt=0)
    if in_stock is False:
        queryset = queryset.filter(in_stock__lte=0)
    queryset = _apply_price_range_filter(queryset, price_range)

    applied_filters = {
        "q": query_normalized,
        "category": category,
        "brand": brand,
        "price_range": price_range,
        "in_stock": in_stock,
        "sort": sort,
    }

    if sort == "price_asc":
        queryset = queryset.order_by("price_value", "-in_stock", "id")
    elif sort == "price_desc":
        queryset = queryset.order_by("-price_value", "-in_stock", "id")
    elif sort == "popular":
        queryset = queryset.order_by("-product_ranking", "-in_stock", "id")
    else:
        queryset = queryset.order_by("-relevance_score", "-product_ranking", "-in_stock", "id")

    facets = _build_facets(queryset)
    total = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = list(queryset[start:end])
    serializer = ProductVariantSerializer(items, many=True)

    took_ms = int((timezone.now() - started_at).total_seconds() * 1000)
    has_more = end < total

    return Response(
        {
            "items": serializer.data,
            "facets": facets,
            "meta": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": has_more,
                "took_ms": took_ms,
                "applied_filters": applied_filters,
            },
        }
    )


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
        
        product = Product.objects.using(STORE_DB_ALIAS).filter(active=True).filter(
            slug__iexact=medicine_slug
        ).first()
        
        if product:
            category = Category.objects.using(STORE_DB_ALIAS).filter(active=True).filter(
                models.Q(path_slug__iexact=cat_path_slug) | 
                models.Q(slug__iexact=cat_path_slug)
            ).first()
            
            if category:
                product_variant = ProductVariant.objects.using(STORE_DB_ALIAS).filter(
                    active=True,
                    product__category=category,
                    product=product
                ).select_related('product', 'product__category').first()
                
                if product_variant:
                    serializer = ProductVariantSerializer(product_variant)
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
        category = Category.objects.using(STORE_DB_ALIAS).filter(active=True).filter(
            models.Q(path_slug__iexact=category_slug) | 
            models.Q(slug__iexact=category_slug)
        ).first()
        
        if not category:
            return Response(
                {'detail': f'Không tìm thấy danh mục hoặc sản phẩm với slug: {category_slug}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        category_path_slug = category.path_slug or category.slug
        
        # Get all subcategory IDs (including nested) for product filtering
        # Use set for efficient duplicate handling
        category_ids = {category.id}
        subcategory_ids = Category.objects.using(STORE_DB_ALIAS).filter(
            active=True,
            path_slug__istartswith=f"{category_path_slug}/"
        ).values_list('id', flat=True)
        category_ids.update(subcategory_ids)
        
        queryset = annotate_variant_unit_price(
            ProductVariant.objects.using(STORE_DB_ALIAS).filter(
                active=True,
                product__category_id__in=list(category_ids),
            ).select_related('product', 'product__category', 'product__brand')
        , db_alias=STORE_DB_ALIAS)
        
        # Get immediate subcategories (always needed for navigation)
        immediate_subcategories = FilterHelpers.get_immediate_subcategories(category)
        has_subcategories = bool(immediate_subcategories)
        
        # Check if category is too large - return subcategories only
        product_count = queryset.count()
        
        if product_count > LARGE_CATEGORY_THRESHOLD:
            # Return subcategories only (no products) when over threshold
            return Response({
                'categorySlug': category_path_slug,
                'categoryName': category.path or category.name,
                'productCount': product_count,
                'hasSubcategories': has_subcategories,
                'subcategories': immediate_subcategories,
                'products': [],  # Empty products list when over threshold
                'overLimit': True
            })
        
    except Exception as e:
        return Response(
            {'detail': f'Lỗi khi tìm kiếm danh mục với slug: {category_slug}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    # Normal flow: return products (product_count <= LARGE_CATEGORY_THRESHOLD)
    # Subcategories already fetched above, reuse them
    filter_backend = DjangoFilterBackend()
    queryset = filter_backend.filter_queryset(request, queryset, ProductFilter)
    
    search_backend = filters.SearchFilter()
    search_backend.search_fields = ['product__name', 'packing', 'product__web_name']
    queryset = search_backend.filter_queryset(request, queryset, None)
    
    # Ensure queryset is always deterministically ordered before pagination.
    # Using OrderingFilter with `view=None` can skip default ordering and trigger
    # UnorderedObjectListWarning in DRF paginator.
    allowed_ordering_fields = {'price_value', 'created_date', 'in_stock', 'product_ranking', 'id'}
    raw_ordering = (request.query_params.get('ordering') or '').strip()
    if raw_ordering:
        parsed_ordering = [part.strip() for part in raw_ordering.split(',') if part.strip()]
        sanitized_ordering = []
        for field in parsed_ordering:
            normalized = field[1:] if field.startswith('-') else field
            if normalized in allowed_ordering_fields:
                sanitized_ordering.append(field)
        queryset = queryset.order_by(*(sanitized_ordering or ['-created_date', '-id']))
    else:
        queryset = queryset.order_by('-created_date', '-id')
    
    paginator = ProductPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        serializer = ProductVariantSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        # Add subcategories to paginated response
        response.data['hasSubcategories'] = has_subcategories
        response.data['subcategories'] = immediate_subcategories
        return response
    
    serializer = ProductVariantSerializer(queryset, many=True)
    return Response({
        'categorySlug': category_path_slug,
        'categoryName': category.path or category.name,
        'productCount': product_count,
        'hasSubcategories': has_subcategories,
        'subcategories': immediate_subcategories,  # Always include subcategories
        'products': serializer.data,
        'overLimit': False
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def contact_support_request(request):
    serializer = ContactSupportRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    request_type_map = {
        'support': 'Hỗ trợ kỹ thuật',
        'policy': 'Chính sách',
        'other': 'Khác',
    }
    request_type_label = request_type_map.get(data.get('request_type', 'support'), 'Hỗ trợ kỹ thuật')
    subject = data.get('subject') or f'Yêu cầu {request_type_label} từ website'

    contact_lines = [
        f"Loại yêu cầu: {request_type_label}",
        f"Họ tên: {data.get('name', '').strip()}",
        f"Email: {data.get('email', '').strip()}",
    ]
    phone = (data.get('phone') or '').strip()
    if phone:
        contact_lines.append(f"Điện thoại: {phone}")
    contact_lines.extend(['', 'Nội dung:', data.get('message', '').strip()])

    notification = Notification.objects.using(STORE_DB_ALIAS).create(
        notification_type=Notification.ADMIN_SUPPORT,
        title=subject,
        message='\n'.join(contact_lines),
        is_read=False,
    )

    return Response(
        {
            'message': 'Gửi yêu cầu thành công. Admin sẽ phản hồi sớm.',
            'notification_id': notification.id,
        },
        status=status.HTTP_201_CREATED,
    )
