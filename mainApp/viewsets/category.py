from rest_framework import viewsets, generics

from mainApp.models import Category
from mainApp.serializers import CategorySerializer

class CategoryViewSet(viewsets.ViewSet, generics.ListAPIView, generics.UpdateAPIView,
                      generics.CreateAPIView, generics.DestroyAPIView):
    queryset = Category.objects.filter(active=True)
    serializer_class = CategorySerializer
