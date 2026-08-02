from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta
from .models import (
    Brand,
    ShippingMethod,
    PaymentMethod,
    Order,
    OrderItem,
    MedicineBatch,
    Notification,
    SearchKeyword,
    Product,
    ProductCategory,
    ProductVariant,
    Category,
    CatalogAttribute,
    CatalogAttributeOption,
    ProductAttributeValue,
)
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

class ProductCategoryInline(admin.TabularInline):
    model = ProductCategory
    extra = 0
    fields = ["category", "is_primary", "sort_order"]
    autocomplete_fields = ["category"]


class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'brand', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name', 'category__name', 'brand__name']
    list_editable = ['active']
    inlines = [ProductCategoryInline]

class ProductVariantAdmin(admin.ModelAdmin):
    """Giá bán nằm trên ProductVariantUnit; hiển thị giá đơn vị mặc định (hoặc đơn vị đầu tiên)."""
    list_display = ['packing', 'product', 'default_unit_price', 'in_stock', 'created_date']
    list_filter = ['in_stock', 'created_date']
    search_fields = ['packing', 'product__name']
    list_editable = ['in_stock']

    @admin.display(description='Giá (đơn vị mặc định)')
    def default_unit_price(self, obj):
        if not obj or not obj.pk:
            return '—'
        u = obj.units.filter(is_default=True).first() or obj.units.order_by('unit_order', 'id').first()
        if u is None:
            return '—'
        return u.price_value

class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'active', 'created_date']
    list_filter = ['active', 'created_date']
    search_fields = ['name']
    list_editable = ['active']

class ExpiryHorizonFilter(admin.SimpleListFilter):
    title = "Expiry risk"
    parameter_name = "expiry_risk"

    def lookups(self, request, model_admin):
        return (
            ("expired", "Expired (still in stock)"),
            ("urgent", "Urgent (≤7 days)"),
            ("warning", "Warning (≤30 days)"),
            ("watch", "Watch (≤90 days)"),
            ("ok", "OK (>90 days)"),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()
        value = self.value()
        stocked = queryset.filter(active=True, remaining_quantity__gt=0)
        if value == "expired":
            return stocked.filter(expiry_date__lt=today)
        if value == "urgent":
            return stocked.filter(
                expiry_date__gte=today, expiry_date__lte=today + timedelta(days=7)
            )
        if value == "warning":
            return stocked.filter(
                expiry_date__gt=today + timedelta(days=7),
                expiry_date__lte=today + timedelta(days=30),
            )
        if value == "watch":
            return stocked.filter(
                expiry_date__gt=today + timedelta(days=30),
                expiry_date__lte=today + timedelta(days=90),
            )
        if value == "ok":
            return stocked.filter(expiry_date__gt=today + timedelta(days=90))
        return queryset


class MedicineBatchAdmin(admin.ModelAdmin):
    list_display = [
        "batch_number",
        "product_variant",
        "import_date",
        "expiry_date",
        "days_left_display",
        "quantity",
        "remaining_quantity",
        "is_expired_display",
        "active",
        "created_date",
    ]
    list_filter = [ExpiryHorizonFilter, "active", "import_date", "expiry_date", "created_date"]
    search_fields = [
        "batch_number",
        "product_variant__sku",
        "product_variant__packing",
        "product_variant__product__name",
    ]
    list_editable = ["active", "remaining_quantity"]
    readonly_fields = ["is_expired_display", "days_left_display"]
    actions = ["deactivate_batches", "zero_remaining_stock"]
    ordering = ["expiry_date"]
    list_per_page = 50
    date_hierarchy = "expiry_date"

    @admin.display(description="Days left", ordering="expiry_date")
    def days_left_display(self, obj):
        days = obj.days_until_expiry
        if days < 0:
            color, label = "#b91c1c", f"Expired ({abs(days)}d)"
        elif days <= 7:
            color, label = "#c2410c", f"{days}d"
        elif days <= 30:
            color, label = "#a16207", f"{days}d"
        else:
            color, label = "#15803d", f"{days}d"
        return format_html(
            '<span style="font-weight:600;color:{}">{}</span>', color, label
        )

    @admin.display(description="Expired", boolean=True)
    def is_expired_display(self, obj):
        return obj.is_expired

    @admin.action(description="Deactivate selected batches")
    def deactivate_batches(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, f"Deactivated {updated} batch(es).")

    @admin.action(description="Write off remaining qty (set to 0)")
    def zero_remaining_stock(self, request, queryset):
        updated = queryset.update(remaining_quantity=0)
        self.message_user(request, f"Wrote off remaining stock on {updated} batch(es).")


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


class CatalogAttributeOptionInline(admin.TabularInline):
    model = CatalogAttributeOption
    extra = 0
    fields = ['slug', 'label', 'sort_order', 'active']


class CatalogAttributeAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'facet_type', 'sort_order', 'is_filterable', 'active']
    list_filter = ['facet_type', 'is_filterable', 'active']
    search_fields = ['code', 'label']
    list_editable = ['sort_order', 'is_filterable', 'active']
    inlines = [CatalogAttributeOptionInline]


class ProductAttributeValueAdmin(admin.ModelAdmin):
    list_display = ['product', 'option', 'active', 'created_date']
    list_filter = ['option__attribute', 'active']
    search_fields = ['product__name', 'product__mid', 'option__slug', 'option__label']
    raw_id_fields = ['product', 'option']


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
admin_site.register(CatalogAttribute, CatalogAttributeAdmin)
admin_site.register(ProductAttributeValue, ProductAttributeValueAdmin)