from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, SerializerMethodField
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import (
    MedicineBatch,
    Brand,
    ShippingMethod,
    PaymentMethod,
    Order,
    OrderItem,
    Notification,
    SearchKeyword,
    Product,
    ProductVariant,
    Category,
    ProductVariantUnit,
    Cart,
    CartItem,
)
from mainApp.serializers import UserSerializer

User = get_user_model()


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
    name = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    product_variant_unit = serializers.PrimaryKeyRelatedField(queryset=ProductVariantUnit.objects.all(), required=False, allow_null=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product_variant', 'product_variant_unit', 'quantity', 'price', 'subtotal', 'name', 'image_url', 'created_date', 'updated_date']
        read_only_fields = ['subtotal', 'name', 'image_url']

    def get_name(self, obj):
        try:
            if obj.product_variant and obj.product_variant.product:
                return f"{obj.product_variant.product.web_name or obj.product_variant.product.name} - {obj.product_variant.packing}"
        except Exception:
            pass
        return None

    def get_image_url(self, obj):
        try:
            if obj.product_variant and obj.product_variant.image:
                from mainApp import cloud_context
                return f'{cloud_context}{obj.product_variant.image}'
            if obj.product_variant and obj.product_variant.images and isinstance(obj.product_variant.images, list) and obj.product_variant.images:
                from mainApp import cloud_context
                first = obj.product_variant.images[0]
                url = first.get('url') if isinstance(first, dict) else (first if isinstance(first, str) else None)
                if url and not url.startswith('http'):
                    return f'{cloud_context}{url}'
                return url or None
        except Exception:
            pass
        return None


class OrderSerializer(ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = SerializerMethodField()
    shipping_method = ShippingMethodSerializer(read_only=True)
    payment_method = PaymentMethodSerializer(read_only=True)
    order_voucher_code = serializers.SerializerMethodField()
    shipping_voucher_code = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'user_id', 'user', 'items', 'subtotal', 
            'shipping_fee', 'total', 'status', 'notes', 
            'shipping_method', 'payment_method', 'shipping_address',
            'discount_amount', 'shipping_discount_amount',
            'order_voucher_code', 'shipping_voucher_code',
            'created_date', 'updated_date'
        ]
        extra_kwargs = {
            'order_number': {'required': False, 'allow_blank': True}
        }
        read_only_fields = [
            'order_number', 'subtotal', 'shipping_fee', 'total',
            'discount_amount', 'shipping_discount_amount', 'status',
            'order_voucher_code', 'shipping_voucher_code',
        ]
    
    def create(self, validated_data):
        if hasattr(self, '_shipping_method'):
            validated_data['shipping_method'] = self._shipping_method
        if hasattr(self, '_payment_method'):
            validated_data['payment_method'] = self._payment_method
        request = self.context.get('request')
        if request and getattr(request, 'user', None) and request.user.is_authenticated:
            validated_data['user_id'] = request.user.id
        if hasattr(self, '_computed_order_fields'):
            validated_data.update(self._computed_order_fields)
        return super().create(validated_data)
    
    def get_user(self, obj):
        if obj.user_id:
            try:
                user = User.objects.get(id=obj.user_id)
                return UserSerializer(user).data
            except User.DoesNotExist:
                return None
        return None

    def get_order_voucher_code(self, obj):
        return obj.order_voucher.code if obj.order_voucher else None

    def get_shipping_voucher_code(self, obj):
        return obj.shipping_voucher.code if obj.shipping_voucher else None


class CartItemSerializer(ModelSerializer):
    name = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    packing = serializers.SerializerMethodField()
    unit_options = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product_variant",
            "product_variant_unit",
            "quantity",
            "unit_price_snapshot",
            "name",
            "packing",
            "unit_options",
            "image_url",
            "created_date",
            "updated_date",
        ]

    def get_name(self, obj):
        try:
            if obj.product_variant and obj.product_variant.product:
                return f"{obj.product_variant.product.web_name or obj.product_variant.product.name} - {obj.product_variant.packing}"
        except Exception:
            return None
        return None

    def get_image_url(self, obj):
        try:
            if obj.product_variant and obj.product_variant.image:
                from mainApp import cloud_context
                return f"{cloud_context}{obj.product_variant.image}"
            if obj.product_variant and obj.product_variant.images and isinstance(obj.product_variant.images, list):
                if not obj.product_variant.images:
                    return None
                first = obj.product_variant.images[0]
                if isinstance(first, dict):
                    url = first.get("url")
                else:
                    url = first if isinstance(first, str) else None
                if not url:
                    return None
                if url.startswith("http"):
                    return url
                from mainApp import cloud_context
                return f"{cloud_context}{url}"
        except Exception:
            return None
        return None

    def get_packing(self, obj):
        try:
            if obj.product_variant_unit and obj.product_variant_unit.unit_name:
                return obj.product_variant_unit.unit_name
            if obj.product_variant and obj.product_variant.packing:
                return obj.product_variant.packing
        except Exception:
            return None
        return None

    def get_unit_options(self, obj):
        try:
            variant = getattr(obj, "product_variant", None)
            if not variant:
                return []
            units = variant.units.filter(is_published=True).order_by("unit_order", "id")
            return [
                {
                    "id": unit.id,
                    "unit_name": unit.unit_name,
                    "is_default": bool(unit.is_default),
                    "price_value": unit.price_value,
                }
                for unit in units
            ]
        except Exception:
            return []


class CartSerializer(ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    shipping_method = ShippingMethodSerializer(read_only=True)
    order_voucher_code = serializers.SerializerMethodField()
    shipping_voucher_code = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "user_id",
            "status",
            "items",
            "shipping_method",
            "subtotal",
            "shipping_fee",
            "discount_amount",
            "shipping_discount_amount",
            "total",
            "version",
            "order_voucher_code",
            "shipping_voucher_code",
            "checkout_order",
            "created_date",
            "updated_date",
        ]
        read_only_fields = fields

    def get_order_voucher_code(self, obj):
        return obj.order_voucher.code if obj.order_voucher else None

    def get_shipping_voucher_code(self, obj):
        return obj.shipping_voucher.code if obj.shipping_voucher else None


class MedicineBatchSerializer(ModelSerializer):
    class Meta:
        model = MedicineBatch
        fields = [
            'id', 'batch_number', 'product_variant', 'import_date', 
            'expiry_date', 'quantity', 'remaining_quantity', 'import_price',
            'is_expired', 'days_until_expiry', 'created_date', 'updated_date'
        ]
        read_only_fields = ['is_expired', 'days_until_expiry']


class NotificationSerializer(ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'product_variant', 'batch',
            'title', 'message', 'is_read', 'read_at', 
            'created_date', 'updated_date'
        ]


class ContactSupportRequestSerializer(serializers.Serializer):
    REQUEST_TYPE_CHOICES = [
        ('support', 'Hỗ trợ kỹ thuật'),
        ('policy', 'Chính sách'),
        ('other', 'Khác'),
    ]

    name = serializers.CharField(max_length=120, allow_blank=False, trim_whitespace=True)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True, trim_whitespace=True)
    message = serializers.CharField(allow_blank=False, trim_whitespace=True)
    request_type = serializers.ChoiceField(
        choices=REQUEST_TYPE_CHOICES,
        required=False,
        default='support',
    )


class SearchKeywordSerializer(ModelSerializer):
    class Meta:
        model = SearchKeyword
        fields = ['id', 'keyword', 'hit_count', 'last_searched_at']


class RecordSearchSerializer(serializers.Serializer):
    """Body cho POST record search: gửi keyword người dùng vừa tìm."""
    keyword = serializers.CharField(max_length=120, allow_blank=False, trim_whitespace=True)


class CategorySerializer(ModelSerializer):
    category_array = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "level", "path", "path_slug", "category_array"]
    
    def get_category_array(self, obj):
        if hasattr(obj, 'get_category_array'):
            return obj.get_category_array()
        return []

class ProductSimpleSerializer(ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "name", "mid", "slug", "web_name", 
            "description", "ingredients", "usage", "dosage", 
            "adverse_effect", "careful", "preservation", 
            "brand"
        ]

class ProductVariantSerializer(ModelSerializer):
    product = ProductSimpleSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    brand = SerializerMethodField()
    image_url = SerializerMethodField()
    category_info = SerializerMethodField()
    price_display = SerializerMethodField()
    price_value = SerializerMethodField()
    compare_at_price = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    default_unit_id = serializers.SerializerMethodField()
    default_unit_name = serializers.SerializerMethodField()
    unit_options = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'in_stock', 'image', 'image_url', 'images', "packing",
            'price_display', 'price_value', 'compare_at_price', 'discount_percent',
            'default_unit_id', 'default_unit_name', 'unit_options',
            'product_ranking', 'is_published', 'is_hot',
            'registration_number', 'base_unit',
            'product', 'category', 'category_info', 'brand', 'active',
            'created_date', 'updated_date'
        ]
        read_only_fields = ['image_url', 'brand', 'category_info']
    
    def get_brand(self, obj):
        if hasattr(obj, 'product') and obj.product and obj.product.brand:
            brand = obj.product.brand
            if brand.active:
                return {
                    'id': brand.id,
                    'name': brand.name,
                    'country': brand.country
                }
        return None
    
    def get_image_url(self, obj):
        if obj.image:
            from mainApp import cloud_context
            return f'{cloud_context}{obj.image}'
        return None
    
    def get_category_info(self, obj):
        if hasattr(obj, 'get_category_info'):
            return obj.get_category_info()
        return {
            'category': [],
            'categoryPath': '',
            'categorySlug': ''
        }

    def _get_default_unit(self, obj):
        prefetched_units = getattr(obj, "prefetched_units", None)
        if prefetched_units is not None:
            for unit in prefetched_units:
                if unit.is_default:
                    return unit
            return prefetched_units[0] if prefetched_units else None

        units_manager = getattr(obj, 'units', None)
        if units_manager is None:
            return None
        return units_manager.filter(is_default=True, is_published=True).first() or units_manager.filter(
            is_published=True
        ).order_by('unit_order', 'id').first()

    def get_price_value(self, obj):
        unit = self._get_default_unit(obj)
        if unit is not None and unit.price_value is not None:
            return unit.price_value
        return 0

    def get_price_display(self, obj):
        unit = self._get_default_unit(obj)
        if unit is not None:
            if unit.price_display:
                return unit.price_display
            if unit.price_value is not None:
                return str(unit.price_value)
        return None

    def get_compare_at_price(self, obj):
        unit = self._get_default_unit(obj)
        if unit is not None and unit.compare_at_price is not None:
            return float(unit.compare_at_price)
        return None

    def get_discount_percent(self, obj):
        unit = self._get_default_unit(obj)
        if unit is None or unit.compare_at_price is None or unit.price_value is None:
            return 0
        try:
            compare = float(unit.compare_at_price)
            price = float(unit.price_value)
        except (TypeError, ValueError):
            return 0
        if compare <= price or compare <= 0:
            return 0
        return int(round((compare - price) / compare * 100))

    def get_default_unit_id(self, obj):
        unit = self._get_default_unit(obj)
        return unit.id if unit else None

    def get_default_unit_name(self, obj):
        unit = self._get_default_unit(obj)
        return unit.unit_name if unit else None

    def get_unit_options(self, obj):
        prefetched_units = getattr(obj, "prefetched_units", None)
        if prefetched_units is not None:
            units = prefetched_units
        else:
            units_manager = getattr(obj, "units", None)
            if units_manager is None:
                return []
            units = units_manager.filter(is_published=True).order_by("unit_order", "id")

        return [
            {
                "unit_id": unit.id,
                "unit_name": unit.unit_name,
                "quantity_in_base": unit.quantity_in_base,
                "price_value": unit.price_value,
                "price_display": unit.price_display,
                "compare_at_price": unit.compare_at_price,
                "is_default": bool(unit.is_default),
            }
            for unit in units
        ]


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

class MinimalProductVariantSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id")
    name = serializers.SerializerMethodField()
    slug = serializers.CharField(source="product.slug")
    web_slug = serializers.SerializerMethodField()

    thumbnail = serializers.SerializerMethodField()
    price_value = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    is_out_of_stock = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = ["id", "product_id", "name", "slug", "web_slug",
        "thumbnail", "price_value", 
        "discount_percent", "packing", "in_stock", 
        "is_out_of_stock", "is_hot", "product_ranking", "badges"]

    def get_name(self, obj):
        return obj.product.web_name or obj.product.name

    def get_web_slug(self, obj):
        category_slug = obj.product.category.path_slug if obj.product and obj.product.category else ""
        medicine_slug = obj.product.slug
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
        return 0

    def get_price_value(self, obj):
        units_manager = getattr(obj, 'units', None)
        if units_manager is None:
            return 0
        unit = units_manager.filter(is_default=True, is_published=True).first() or units_manager.filter(
            is_published=True
        ).order_by('unit_order', 'id').first()
        if unit is not None and unit.price_value is not None:
            return unit.price_value
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
        """
        Top selling variants under this level-1 category (subtree), one variant per product.
        Uses ProductVariant.product_ranking (and is_hot) for ordering.
        """
        slug = (obj.path_slug or "").strip()
        if slug:
            category_q = (
                Q(product__category_id=obj.pk)
                | Q(product__category__path_slug=slug)
                | Q(product__category__path_slug__startswith=f"{slug}/")
            )
        else:
            category_q = Q(product__category_id=obj.pk)

        qs = (
            ProductVariant.objects.filter(is_published=True)
            .filter(category_q)
            .select_related("product", "product__category")
            .order_by("-product_ranking", "-is_hot", "-id")
        )
        picked = []
        seen_products = set()
        for variant in qs[:40]:
            pid = variant.product_id
            if pid in seen_products:
                continue
            seen_products.add(pid)
            picked.append(variant)
            if len(picked) >= 5:
                break
        return MinimalProductVariantSerializer(picked, many=True).data


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
            level1_categories = list(Category.objects.filter(
                parent=obj,
                level=1,
                active=True
            ).order_by('name'))
        if level1_categories:
            level1_ids = [cat.id for cat in level1_categories]
            level2_all = Category.objects.filter(
                parent_id__in=level1_ids,
                level=2,
                active=True
            ).order_by('parent_id', 'name')

            from django.db.models import Count
            level2_counts = Category.objects.filter(
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