from django.urls import path, include, re_path
from rest_framework import routers
from .viewsets import (
    BrandViewSet,
    ShippingMethodViewSet,
    PaymentMethodViewSet,
    OrderViewSet,
    OrderItemViewSet,
    MedicineBatchViewSet,
    NotificationViewSet,
    ProductViewSet,
    CategoryViewSet,
)
from .views import products_by_category_slug

router = routers.DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("shipping-methods", ShippingMethodViewSet, basename="shipping-method")
router.register("payment-methods", PaymentMethodViewSet, basename="payment-method")
router.register("orders", OrderViewSet, basename="order")
router.register("order-items", OrderItemViewSet, basename="order-item")
router.register("medicine-batches", MedicineBatchViewSet, basename="medicine-batch")
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    # Router URLs (các routes khác như /products/, /categories/, etc.)
    # Phải đặt router trước regex route để các API endpoints được match đúng
    path('', include(router.urls)),
    # Custom route cho category slug (đặt sau router để chỉ match khi không phải API endpoint)
    # Hỗ trợ nested paths như: thuc-pham-chuc-nang/vitamin-khoang-chat
    # Trailing slash là optional (/?)
    # Exclude các API endpoint names để tránh conflict
    re_path(
        r'^(?!products|categories|brands|shipping-methods|payment-methods|orders|order-items|medicine-batches|notifications)(?P<category_slug>[\w\-/]+)/?$', 
        products_by_category_slug, 
        name='products-by-category-slug'
    ),
]