from django.db import ProgrammingError
from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.parsers import JSONParser

from storeApp.models import SearchKeyword
from storeApp.serializers import SearchKeywordSerializer, RecordSearchSerializer

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def _record_search(keyword: str) -> SearchKeyword:
    """Tăng hit_count nếu đã có (iexact), không thì tạo mới."""
    obj = SearchKeyword.objects.filter(keyword__iexact=keyword).first()
    if obj:
        obj.hit_count += 1
        obj.save(update_fields=["hit_count", "last_searched_at"])
        return obj
    return SearchKeyword.objects.create(keyword=keyword, hit_count=1)


def _is_table_missing(exc: Exception) -> bool:
    return "store_search_keyword" in str(exc) and "does not exist" in str(exc).lower()


class SearchTermsViewSet(viewsets.ViewSet):
    """
    GET list: từ khóa tìm kiếm phổ biến (theo hit_count).
    POST create: ghi nhận một lần tìm kiếm (tăng hit_count hoặc tạo mới).
    """
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def list(self, request):
        try:
            limit = min(int(request.query_params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        qs = SearchKeyword.objects.order_by("-hit_count", "-last_searched_at")[:limit]
        return Response(SearchKeywordSerializer(qs, many=True).data)

    def create(self, request):
        ser = RecordSearchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        keyword = (ser.validated_data["keyword"] or "").strip()
        if not keyword:
            return Response(
                {"keyword": ["Không được để trống."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            obj = _record_search(keyword)
            return Response(SearchKeywordSerializer(obj).data, status=status.HTTP_201_CREATED)
        except ProgrammingError as e:
            if _is_table_missing(e):
                return Response(
                    {"detail": "SearchKeyword table chưa có. Chạy: python manage.py migrate storeApp --database=store"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            raise
