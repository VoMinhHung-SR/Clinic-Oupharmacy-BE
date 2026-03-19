from django.contrib import admin
from .models import Brand, ShippingMethod, PaymentMethod, Order, OrderItem, MedicineBatch, Notification, SearchKeyword, Product, ProductVariant, Category
from mainApp.admin import admin_site


class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'active', 'created_date']
    list_filter = ['country', 'active']
    search_fields = ['name', 'country']
    list_editable = ['active']


class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'estimated_days', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name']
    list_editable = ['active', 'price']


class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name', 'code']
    list_editable = ['active']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product_variant', 'quantity', 'price', 'subtotal', 'created_date']
    fields = ['product_variant', 'quantity', 'price', 'subtotal', 'created_date']


class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'user_id', 'status', 'total', 'payment_method', 'created_date']
    list_filter = ['status', 'payment_method', 'shipping_method', 'created_date']
    search_fields = ['order_number', 'shipping_address']
    readonly_fields = ['order_number', 'created_date', 'updated_date']
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Thông tin đơn hàng', {
            'fields': ('order_number', 'user_id', 'status', 'created_date', 'updated_date')
        }),
        ('Thông tin giao hàng', {
            'fields': ('shipping_address', 'shipping_method', 'shipping_fee')
        }),
        ('Thanh toán', {
            'fields': ('payment_method', 'subtotal', 'total')
        }),
        ('Ghi chú', {
            'fields': ('notes',)
        }),
    )

class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'brand', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name', 'category__name', 'brand__name']
    list_editable = ['active']

class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['packing', 'product', 'price_value', 'in_stock', 'created_date']
    list_filter = ['in_stock', 'created_date']
    search_fields = ['packing', 'product__name']
    list_editable = ['in_stock', 'price_value']

class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name']
    list_editable = ['active']

class MedicineBatchAdmin(admin.ModelAdmin):
    list_display = ['batch_number', 'product_variant', 'import_date', 'expiry_date', 'quantity', 'remaining_quantity', 'is_expired', 'created_date']
    list_filter = ['import_date', 'expiry_date', 'created_date']
    search_fields = ['batch_number', 'product_variant__sku_name']
    readonly_fields = ['is_expired', 'days_until_expiry']
    
    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Hết hạn'


class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'notification_type', 'is_read', 'product_variant', 'created_date']
    list_filter = ['notification_type', 'is_read', 'created_date']
    search_fields = ['title', 'message']
    list_editable = ['is_read']
    readonly_fields = ['created_date', 'updated_date']


class SearchKeywordAdmin(admin.ModelAdmin):
    list_display = ['keyword', 'hit_count', 'last_searched_at', 'created_date']
    list_filter = ['created_date']
    search_fields = ['keyword']
    ordering = ['-hit_count']


# Đăng ký với custom admin site
admin_site.register(Brand, BrandAdmin)
admin_site.register(ShippingMethod, ShippingMethodAdmin)
admin_site.register(PaymentMethod, PaymentMethodAdmin)
admin_site.register(Order, OrderAdmin)
admin_site.register(OrderItem)
admin_site.register(MedicineBatch, MedicineBatchAdmin)
admin_site.register(Notification, NotificationAdmin)
admin_site.register(SearchKeyword, SearchKeywordAdmin)
admin_site.register(Category, CategoryAdmin)
admin_site.register(Product, ProductAdmin)
admin_site.register(ProductVariant, ProductVariantAdmin)