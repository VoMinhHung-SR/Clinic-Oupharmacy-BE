from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, SerializerMethodField
from .models import MedicineBatch, Brand, ShippingMethod, PaymentMethod, Order, OrderItem, Notification
from mainApp.serializers import UserSerializer, MedicineSerializer, CategorySerializer
from mainApp.models import User, MedicineUnit, Category, Medicine


class BrandSerializer(ModelSerializer):
    class Meta:
        model = Brand
        fields = ['id', 'name', 'active', 'country']


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
        extra_kwargs = {
            'order_number': {'required': False, 'allow_blank': True}
        }
    
    def create(self, validated_data):
        if hasattr(self, '_shipping_method'):
            validated_data['shipping_method'] = self._shipping_method
        if hasattr(self, '_payment_method'):
            validated_data['payment_method'] = self._payment_method
            
        return super().create(validated_data)
    
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
    images_urls = SerializerMethodField()
    category_info = SerializerMethodField()
    
    class Meta:
        model = MedicineUnit
        fields = [
            'id', 'in_stock', 'image', 'image_url', 'images', 'images_urls',
            'price_display', 'price_value', 'package_size', 'prices', 'price_obj',
            'link', 'product_ranking', 'display_code', 'is_published',
            'registration_number', 'origin', 'manufacturer', 'shelf_life', 'specifications',
            'medicine', 'category', 'category_info', 'brand', 'active',
            'created_date', 'updated_date'
        ]
        read_only_fields = ['image_url', 'images_urls', 'brand', 'category_info']
    
    def get_brand(self, obj):
        if hasattr(obj, 'medicine') and obj.medicine and obj.medicine.brand_id:
            try:
                brand = Brand.objects.get(id=obj.medicine.brand_id, active=True)
                return {
                    'id': brand.id,
                    'name': brand.name,
                    'country': brand.country
                }
            except Brand.DoesNotExist:
                return None
        return None
    
    def get_image_url(self, obj):
        if obj.image:
            from mainApp import cloud_context
            return f'{cloud_context}{obj.image}'
        return None
    
    def get_images_urls(self, obj):
        """Convert images array to full URLs"""
        if obj.images and isinstance(obj.images, list):
            from mainApp import cloud_context
            return [f'{cloud_context}{img}' if img else None for img in obj.images]
        return []
    
    def get_category_info(self, obj):
        """Get category info in format: {category: [...], categoryPath: '...', categorySlug: '...'}"""
        if hasattr(obj, 'get_category_info'):
            return obj.get_category_info()
        return {
            'category': [],
            'categoryPath': '',
            'categorySlug': ''
        }


class CategoryLevel2Serializer(ModelSerializer):
    """Serializer cho category level 2 với thông tin total"""
    total = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'path_slug', 'total']
    
    def get_total(self, obj):
        if hasattr(obj, '_level2_total'):
            return obj._level2_total
        return None

class MinimalMedicineUnitSerializer(serializers.ModelSerializer):
    medicine_id = serializers.IntegerField(source="medicine.id")
    name = serializers.SerializerMethodField()
    slug = serializers.CharField(source="medicine.slug")
    web_slug = serializers.SerializerMethodField()

    thumbnail = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    is_out_of_stock = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()

    class Meta:
        model = MedicineUnit
        fields = ["id", "medicine_id", "name", "slug", "web_slug",
        "thumbnail", "price_value", "original_price_value", 
        "discount_percent", "package_size", "in_stock", 
        "is_out_of_stock", "is_hot", "product_ranking", "badges"]

    def get_name(self, obj):
        return obj.medicine.web_name or obj.medicine.name

    def get_web_slug(self, obj):
        category_slug = obj.category.path_slug if obj.category else ""
        medicine_slug = obj.medicine.slug
        if category_slug:
            return f"{category_slug}/{medicine_slug}"
        return medicine_slug

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if 'web_slug' in data:
            data['web-slug'] = data.pop('web_slug')
        return data

    def get_thumbnail(self, obj):
        if obj.image:
            try:
                from mainApp import cloud_context
                return f"{cloud_context}{obj.image}"
            except Exception:
                pass

        images = obj.images or []
        if images and isinstance(images, list):
            first = images[0]
            if isinstance(first, str):
                from mainApp import cloud_context
                if first.startswith('http'):
                    return first
                return f"{cloud_context}{first}"
            if isinstance(first, dict):
                return first.get("url")
        return None

    def get_discount_percent(self, obj):
        if (
            obj.original_price_value
            and obj.original_price_value > obj.price_value
        ):
            return int(
                (obj.original_price_value - obj.price_value)
                / obj.original_price_value * 100
            )
        return 0

    def get_is_out_of_stock(self, obj):
        return obj.in_stock <= 0

    def get_badges(self, obj):
        badges = []

        if obj.is_hot:
            badges.append("hot")

        if obj.product_ranking >= 80:
            badges.append("best_seller")

        if self.get_discount_percent(obj) >= 15:
            badges.append("discount")

        return badges


class CategoryLevel1Serializer(ModelSerializer):
    level2 = SerializerMethodField()
    top_products = SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "path_slug", "level2", "top_products"]

    def get_level2(self, obj):
        if hasattr(obj, "_prefetched_objects_cache") and "children" in obj._prefetched_objects_cache:
            level2_categories = [
                child
                for child in obj._prefetched_objects_cache["children"]
                if child.level == 2 and child.active
            ][:5]
        else:
            level2_categories = Category.objects.filter(
                parent=obj,
                level=2,
                active=True,
            )[:5]

        return CategoryLevel2Serializer(level2_categories, many=True).data

    def get_top_products(self, obj):
        from .services.medicine_ranking import get_top5_medicine_units_for_category

        products = get_top5_medicine_units_for_category(obj)
        return MinimalMedicineUnitSerializer(products, many=True).data


class CategoryLevel0Serializer(ModelSerializer):
    """Serializer cho category level 0 với children level 1"""
    level1 = SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'path_slug', 'level1']
    
    def get_level1(self, obj):
        """Lấy tất cả categories level 1 thuộc category này"""
        if hasattr(obj, '_prefetched_objects_cache') and 'children' in obj._prefetched_objects_cache:
            level1_categories = list(obj._prefetched_objects_cache['children'])
        else:
            level1_categories = list(Category.objects.using('default').filter(
                parent=obj,
                level=1,
                active=True
            ).order_by('name'))
        
        if level1_categories:
            level1_ids = [cat.id for cat in level1_categories]
            level2_all = Category.objects.using('default').filter(
                parent_id__in=level1_ids,
                level=2,
                active=True
            ).order_by('parent_id', 'name')
            
            from django.db.models import Count
            level2_counts = Category.objects.using('default').filter(
                level=2,
                active=True,
                parent_id__in=level1_ids
            ).values('parent_id').annotate(total=Count('id'))
            
            count_dict = {item['parent_id']: item['total'] for item in level2_counts}
            
            level2_by_parent = {}
            for l2 in level2_all:
                parent_id = l2.parent_id
                if parent_id not in level2_by_parent:
                    level2_by_parent[parent_id] = []
                
                if len(level2_by_parent[parent_id]) < 5:
                    total = count_dict.get(parent_id, 0)
                    if total > 5:
                        l2._level2_total = total
                    level2_by_parent[parent_id].append(l2)
            
            for l1 in level1_categories:
                if not hasattr(l1, '_prefetched_objects_cache'):
                    l1._prefetched_objects_cache = {}
                l1._prefetched_objects_cache['children'] = level2_by_parent.get(l1.id, [])
        
        return CategoryLevel1Serializer(level1_categories, many=True).data