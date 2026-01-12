"""
Dynamic Filters ViewSet - API endpoint for dynamic filters
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from storeApp.services.dynamic_filters_service import DynamicFiltersService

logger = logging.getLogger(__name__)


class DynamicFiltersViewSet(viewsets.ViewSet):
    """
    ViewSet để trả về dynamic filters dựa trên category slug
    Chỉ xử lý HTTP requests/responses, business logic nằm trong Service Layer
    """
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'], url_path='(?P<category_slug>[\w\-/]+)')
    def get_filters(self, request, category_slug=None):
        """
        GET /api/store/dynamic-filters/{category_slug}/
        
        Trả về bộ lọc động dựa trên category slug
        Hỗ trợ nested paths: thuc-pham-chuc-nang/vitamin-khoang-chat
        
        Query Parameters:
            - use_cache: bool (default: True) - Whether to use cache
        """
        if not category_slug:
            return Response(
                {'detail': 'Category slug is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        category_slug = category_slug.rstrip('/')
        
        # Check if cache should be used
        use_cache = request.query_params.get('use_cache', 'true').lower() != 'false'
        
        try:
            # Get filters from service layer
            filters_data = DynamicFiltersService.get_category_filters(
                category_slug=category_slug,
                use_cache=use_cache
            )
            
            if filters_data is None:
                return Response(
                    {'detail': f'Không tìm thấy danh mục với slug: {category_slug}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            return Response(filters_data)
            
        except Exception as e:
            logger.error(f'Error getting filters for category {category_slug}: {str(e)}', exc_info=True)
            return Response(
                {'detail': f'Lỗi khi lấy filters: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
