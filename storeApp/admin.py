from django.contrib import admin
from .models import Brand, ShippingMethod, PaymentMethod, Order, OrderItem


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name']
    list_editable = ['active']


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'estimated_days', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name']
    list_editable = ['active', 'price']


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name', 'code']
    list_editable = ['active']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['medicine_unit_id', 'quantity', 'price', 'created_date']
    fields = ['medicine_unit_id', 'quantity', 'price', 'subtotal', 'created_date']


@admin.register(Order)
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
