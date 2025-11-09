from django.urls import path, include
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
    path('', include(router.urls)),
]