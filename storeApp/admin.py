from django.contrib import admin
from .models import Brand, ShippingMethod, PaymentMethod, Order, OrderItem, MedicineBatch, Notification
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
    readonly_fields = ['medicine_unit_id', 'quantity', 'price', 'subtotal', 'created_date']
    fields = ['medicine_unit_id', 'quantity', 'price', 'subtotal', 'created_date']


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


class MedicineBatchAdmin(admin.ModelAdmin):
    list_display = ['batch_number', 'medicine_unit_id', 'import_date', 'expiry_date', 'quantity', 'remaining_quantity', 'is_expired', 'created_date']
    list_filter = ['import_date', 'expiry_date', 'created_date']
    search_fields = ['batch_number', 'medicine_unit_id']
    readonly_fields = ['is_expired', 'days_until_expiry']
    
    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Hết hạn'


class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'notification_type', 'is_read', 'medicine_unit_id', 'created_date']
    list_filter = ['notification_type', 'is_read', 'created_date']
    search_fields = ['title', 'message']
    list_editable = ['is_read']
    readonly_fields = ['created_date', 'updated_date']


# Đăng ký với custom admin site
admin_site.register(Brand, BrandAdmin)
admin_site.register(ShippingMethod, ShippingMethodAdmin)
admin_site.register(PaymentMethod, PaymentMethodAdmin)
admin_site.register(Order, OrderAdmin)
admin_site.register(OrderItem)
admin_site.register(MedicineBatch, MedicineBatchAdmin)
admin_site.register(Notification, NotificationAdmin)
