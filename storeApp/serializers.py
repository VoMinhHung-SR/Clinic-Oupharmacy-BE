from rest_framework.serializers import ModelSerializer, SerializerMethodField
from .models import MedicineBatch, Brand, ShippingMethod, PaymentMethod, Order, OrderItem, Notification
from mainApp.serializers import UserSerializer, MedicineSerializer, CategorySerializer
from mainApp.models import User, MedicineUnit


class BrandSerializer(ModelSerializer):
    class Meta:
        model = Brand
        fields = ['id', 'name', 'active', 'created_date', 'updated_date']


class ShippingMethodSerializer(ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = ['id', 'name', 'price', 'estimated_days', 'active', 'created_date', 'updated_date']


class PaymentMethodSerializer(ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'name', 'code', 'active', 'created_date', 'updated_date']


class OrderItemSerializer(ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'medicine_unit_id', 'quantity', 'price', 'subtotal', 'created_date', 'updated_date']
        read_only_fields = ['subtotal']


class OrderSerializer(ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = SerializerMethodField()
    shipping_method = ShippingMethodSerializer(read_only=True)
    payment_method = PaymentMethodSerializer(read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'user_id', 'user', 'items', 'subtotal', 
            'shipping_fee', 'total', 'status', 'notes', 
            'shipping_method', 'payment_method', 'shipping_address',
            'created_date', 'updated_date'
        ]
    
    def get_user(self, obj):
        if obj.user_id:
            try:
                user = User.objects.get(id=obj.user_id)
                return UserSerializer(user).data
            except User.DoesNotExist:
                return None
        return None


class MedicineBatchSerializer(ModelSerializer):
    class Meta:
        model = MedicineBatch
        fields = [
            'id', 'batch_number', 'medicine_unit_id', 'import_date', 
            'expiry_date', 'quantity', 'remaining_quantity', 'import_price',
            'is_expired', 'days_until_expiry', 'created_date', 'updated_date'
        ]
        read_only_fields = ['is_expired', 'days_until_expiry']


class NotificationSerializer(ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'medicine_unit_id', 'batch_id',
            'title', 'message', 'is_read', 'read_at', 
            'created_date', 'updated_date'
        ]


class ProductSerializer(ModelSerializer):
    medicine = MedicineSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    brand = SerializerMethodField()
    image_url = SerializerMethodField()
    
    class Meta:
        model = MedicineUnit
        fields = [
            'id', 'price', 'in_stock', 'image', 'image_url', 'packaging',
            'medicine', 'category', 'brand_id', 'brand', 'active',
            'created_date', 'updated_date'
        ]
        read_only_fields = ['image_url', 'brand']
    
    def get_brand(self, obj):
        if obj.brand_id:
            try:
                brand = Brand.objects.get(id=obj.brand_id, active=True)
                return {
                    'id': brand.id,
                    'name': brand.name
                }
            except Brand.DoesNotExist:
                return None
        return None
    
    def get_image_url(self, obj):
        if obj.image:
            from mainApp import cloud_context
            return f'{cloud_context}{obj.image}'
        return None