from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db.models import Prefetch
from storeApp.models import Category
from storeApp.serializers import CategoryLevel0Serializer


class CategoryViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView):
    queryset = Category.objects.filter(active=True).order_by('name')
    # Use Level0Serializer here or a default one as before... Wait, previous it was CategorySerializer
    # Let's import CategorySerializer from storeApp.serializers and use it here
    from storeApp.serializers import CategorySerializer
    serializer_class = CategorySerializer
    parser_classes = [JSONParser]
    permission_classes = [AllowAny]
    
    def list(self, request, *args, **kwargs):
        """
        GET /api/store/categories/
        Trả về categories theo cấu trúc nested: level0 -> level1 -> level2 (top 5)
        """
        level1_prefetch = Prefetch(
            'children',
            queryset=Category.objects.filter(
                level=1,
                active=True
            ).order_by('name')
        )
        
        level0_categories = Category.objects.filter(
            level=0,
            active=True
        ).prefetch_related(level1_prefetch).order_by('name')
        
        serializer = CategoryLevel0Serializer(level0_categories, many=True)
        return Response(serializer.data)