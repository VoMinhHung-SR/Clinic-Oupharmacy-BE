from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib import admin, messages
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html

from mainApp.authz import is_business_admin
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
    Campaign,
    CampaignPlacement,
    CampaignProduct,
    CampaignCategory,
    CampaignVoucher,
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


class CurrentCampaignFilter(admin.SimpleListFilter):
    """Default: programs ops actually care about (not ended/archived drafts dump)."""

    title = "Current programs"
    parameter_name = "window"

    def lookups(self, request, model_admin):
        return (
            ("current", "Current (active / scheduled / paused)"),
            ("live", "Live in window (active now)"),
            ("all", "All statuses"),
        )

    def value(self):
        selected = super().value()
        return selected if selected is not None else "current"

    def queryset(self, request, queryset):
        now = timezone.now()
        value = self.value()
        if value == "all":
            return queryset
        if value == "live":
            in_window = (Q(start_at__isnull=True) | Q(start_at__lte=now)) & (
                Q(end_at__isnull=True) | Q(end_at__gt=now)
            )
            return queryset.filter(status=Campaign.STATUS_ACTIVE).filter(in_window)
        return queryset.filter(
            status__in=[
                Campaign.STATUS_ACTIVE,
                Campaign.STATUS_SCHEDULED,
                Campaign.STATUS_PAUSED,
            ]
        )


class CampaignPlacementInline(admin.TabularInline):
    model = CampaignPlacement
    extra = 1
    fields = [
        "slot",
        "title",
        "subtitle",
        "cta_label",
        "cta_url",
        "image_desktop_url",
        "image_mobile_url",
        "image_alt",
        "is_enabled",
        "sort_order",
    ]


class CampaignProductInline(admin.TabularInline):
    model = CampaignProduct
    extra = 1
    fields = ["product_mid", "sort_order"]


class CampaignCategoryInline(admin.TabularInline):
    model = CampaignCategory
    extra = 1
    fields = ["category_slug", "sort_order"]


class CampaignVoucherInline(admin.TabularInline):
    model = CampaignVoucher
    extra = 1
    fields = ["voucher", "is_featured", "sort_order"]
    raw_id_fields = ["voucher"]


class CampaignAdmin(admin.ModelAdmin):
    """Jazzmin campaign CMS (D-18). Status changes go through CampaignService actions."""

    list_display = [
        "name",
        "slug",
        "status",
        "priority",
        "start_at",
        "end_at",
        "in_window_display",
        "active",
        "version",
    ]
    list_filter = [CurrentCampaignFilter, "status", "active", "locale"]
    search_fields = ["name", "slug", "title"]
    ordering = ["-priority", "start_at", "id"]
    list_per_page = 50

    def get_prepopulated_fields(self, request, obj=None):
        if obj:
            return {}
        return {"slug": ("name",)}
    inlines = [
        CampaignPlacementInline,
        CampaignProductInline,
        CampaignCategoryInline,
        CampaignVoucherInline,
    ]
    actions = [
        "action_schedule",
        "action_publish",
        "action_pause",
        "action_resume",
        "action_end",
        "action_archive",
    ]
    fieldsets = (
        (
            "Campaign",
            {
                "description": (
                    "Store merchandising CMS. Change status with the list actions "
                    "(schedule / publish / pause / resume / end / archive) so "
                    "<code>CampaignService</code> + public cache stay consistent. "
                    "Do not edit <code>status</code> by hand."
                ),
                "fields": ("name", "slug", "title", "subtitle", "description_html", "locale", "active"),
            },
        ),
        (
            "Schedule & ranking",
            {"fields": ("status", "priority", "start_at", "end_at", "in_window_display", "version")},
        ),
        (
            "Storefront preview",
            {"fields": ("preview_store_link",)},
        ),
        (
            "Audit",
            {"fields": ("created_by_id", "updated_by_id", "created_date", "updated_date")},
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        ro = [
            "status",
            "version",
            "created_by_id",
            "updated_by_id",
            "created_date",
            "updated_date",
            "in_window_display",
            "preview_store_link",
        ]
        if obj:
            return ["slug", *ro]
        return ro

    @admin.display(description="Preview on store")
    def preview_store_link(self, obj):
        if not obj or not obj.pk or not obj.slug:
            return "—"
        from storeApp.services.campaign_preview import sign_campaign_preview

        token = sign_campaign_preview(obj)
        base = getattr(settings, "STOREFRONT_PUBLIC_URL", "http://localhost:3000").rstrip("/")
        url = f"{base}/khuyen-mai/{obj.slug}?preview={quote(token, safe='')}"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Xem trước trên store</a>',
            url,
        )

    @admin.display(description="In window", boolean=True)
    def in_window_display(self, obj):
        now = timezone.now()
        start_ok = obj.start_at is None or obj.start_at <= now
        end_ok = obj.end_at is None or obj.end_at > now
        return bool(obj.status == Campaign.STATUS_ACTIVE and start_ok and end_ok)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "placements", "products", "categories", "voucher_links"
        )

    def has_module_permission(self, request):
        return is_business_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_business_admin(request.user)

    def has_add_permission(self, request):
        return is_business_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_business_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_business_admin(request.user):
            return False
        if obj is None:
            return False
        return obj.status == Campaign.STATUS_DRAFT

    def save_model(self, request, obj, form, change):
        uid = getattr(request.user, "id", None)
        if not change:
            obj.status = Campaign.STATUS_DRAFT
            obj.created_by_id = uid
            obj.updated_by_id = uid
            if not obj.version:
                obj.version = 1
            super().save_model(request, obj, form, change)
            self._invalidate_cache()
            return
        obj.updated_by_id = uid
        obj.version = (obj.version or 1) + 1
        super().save_model(request, obj, form, change)
        self._invalidate_cache()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if change:
            self._invalidate_cache()

    @staticmethod
    def _invalidate_cache():
        from storeApp.services.campaign_cache import invalidate_public_campaign_cache

        invalidate_public_campaign_cache()

    def _run_lifecycle(self, request, queryset, action_fn, label):
        from storeApp.services.campaign_service import CampaignServiceError

        ok = 0
        for campaign in queryset:
            try:
                action_fn(
                    campaign_id=campaign.id,
                    expected_version=campaign.version,
                    actor_user_id=request.user.id,
                )
                ok += 1
            except CampaignServiceError as exc:
                self.message_user(request, f"{campaign.slug}: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"{label}: {ok} campaign(s).", level=messages.SUCCESS)

    @admin.action(description="Schedule (draft → scheduled)")
    def action_schedule(self, request, queryset):
        from storeApp.services.campaign_service import schedule_campaign

        self._run_lifecycle(request, queryset, schedule_campaign, "Scheduled")

    @admin.action(description="Publish now (→ active)")
    def action_publish(self, request, queryset):
        from storeApp.services.campaign_service import publish_campaign

        self._run_lifecycle(request, queryset, publish_campaign, "Published")

    @admin.action(description="Pause (active → paused)")
    def action_pause(self, request, queryset):
        from storeApp.services.campaign_service import pause_campaign

        self._run_lifecycle(request, queryset, pause_campaign, "Paused")

    @admin.action(description="Resume (paused → active)")
    def action_resume(self, request, queryset):
        from storeApp.services.campaign_service import resume_campaign

        self._run_lifecycle(request, queryset, resume_campaign, "Resumed")

    @admin.action(description="End campaign")
    def action_end(self, request, queryset):
        from storeApp.services.campaign_service import end_campaign

        self._run_lifecycle(request, queryset, end_campaign, "Ended")

    @admin.action(description="Archive")
    def action_archive(self, request, queryset):
        from storeApp.services.campaign_service import archive_campaign

        self._run_lifecycle(request, queryset, archive_campaign, "Archived")


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
admin_site.register(Campaign, CampaignAdmin)