from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser
from mainApp.models import Category
from mainApp.serializers import CategorySerializer


class CategoryViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView):
    queryset = Category.objects.using('default').filter(active=True).order_by('name')
    serializer_class = CategorySerializer
    parser_classes = [JSONParser]

