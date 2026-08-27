"""Campaign models: core + placements (P1) + catalog scope (P4). Voucher/order attribution later."""

from django.db import models

from mainApp.models import BaseModel


class Campaign(BaseModel):
    STATUS_DRAFT = "draft"
    STATUS_SCHEDULED = "scheduled"
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_ENDED = "ended"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_ENDED, "Ended"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    name = models.CharField(max_length=120, db_column="name")
    slug = models.SlugField(max_length=80, unique=True, db_column="slug", db_index=True)
    title = models.CharField(max_length=160, db_column="title")
    subtitle = models.CharField(max_length=255, null=True, blank=True, db_column="subtitle")
    description_html = models.TextField(null=True, blank=True, db_column="description_html")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_column="status",
        db_index=True,
    )
    priority = models.IntegerField(default=0, db_column="priority")
    start_at = models.DateTimeField(null=True, blank=True, db_column="start_at", db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_column="end_at", db_index=True)
    locale = models.CharField(max_length=10, default="vi", db_column="locale")
    # Cross-DB user refs (mainApp.User on default DB) — store BigInteger ids, not FK.
    created_by_id = models.BigIntegerField(null=True, blank=True, db_column="created_by_id", db_index=True)
    updated_by_id = models.BigIntegerField(null=True, blank=True, db_column="updated_by_id")
    version = models.PositiveIntegerField(default=1, db_column="version")

    class Meta:
        db_table = "store_campaign"
        verbose_name = "Campaign"
        verbose_name_plural = "Campaigns"
        ordering = ["-priority", "start_at", "id"]
        indexes = [
            models.Index(fields=["status", "start_at", "end_at"], name="campaign_status_window_idx"),
            models.Index(fields=["-priority", "start_at"], name="campaign_priority_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(end_at__isnull=True)
                    | models.Q(start_at__isnull=True)
                    | models.Q(end_at__gt=models.F("start_at"))
                ),
                name="campaign_end_after_start",
            ),
            models.CheckConstraint(
                check=models.Q(
                    status__in=[
                        "draft",
                        "scheduled",
                        "active",
                        "paused",
                        "ended",
                        "archived",
                    ]
                ),
                name="campaign_status_valid",
            ),
        ]
        permissions = [
            ("campaign_view", "Can view store campaigns"),
            ("campaign_manage", "Can manage store campaigns"),
        ]

    def __str__(self):
        return f"{self.slug} ({self.status})"


class CampaignPlacement(BaseModel):
    # D-21 taxonomy (P9). Legacy LEFT/STRIP/RIGHT removed from choices after data migration.
    SLOT_HOME_HERO = "HOME_HERO"
    SLOT_HOME_SECONDARY = "HOME_SECONDARY"
    SLOT_HOME_NOTICE_TOP = "HOME_NOTICE_TOP"
    SLOT_HOME_NOTICE_BOTTOM = "HOME_NOTICE_BOTTOM"
    SLOT_CATEGORY_BANNER = "CATEGORY_BANNER"
    SLOT_SEARCH_BANNER = "SEARCH_BANNER"
    # Read aliases for one-release safety / incoming query params (D-21).
    SLOT_LEGACY_ALIASES = {
        "HOME_PROMO_LEFT": SLOT_HOME_SECONDARY,
        "HOME_STRIP": SLOT_HOME_NOTICE_TOP,
        "HOME_PROMO_RIGHT": SLOT_HOME_NOTICE_BOTTOM,
    }
    SLOT_CHOICES = [
        (SLOT_HOME_HERO, "Banner chính (Hero)"),
        (SLOT_HOME_SECONDARY, "Banner phụ (Secondary)"),
        (SLOT_HOME_NOTICE_TOP, "Thông báo phải — trên"),
        (SLOT_HOME_NOTICE_BOTTOM, "Thông báo phải — dưới"),
        (SLOT_CATEGORY_BANNER, "Category banner"),
        (SLOT_SEARCH_BANNER, "Search banner"),
    ]
    CAROUSEL_SLOTS = frozenset({SLOT_HOME_HERO, SLOT_HOME_SECONDARY})
    SLOT_SLIDE_CAPS = {
        SLOT_HOME_HERO: 3,
        SLOT_HOME_SECONDARY: 5,
    }

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="placements",
        db_column="campaign_id",
    )
    slot = models.CharField(max_length=40, choices=SLOT_CHOICES, db_column="slot", db_index=True)
    title = models.CharField(max_length=160, db_column="title")
    subtitle = models.CharField(max_length=255, null=True, blank=True, db_column="subtitle")
    cta_label = models.CharField(max_length=80, null=True, blank=True, db_column="cta_label")
    cta_url = models.CharField(max_length=500, null=True, blank=True, db_column="cta_url")
    image_desktop_url = models.CharField(max_length=500, null=True, blank=True, db_column="image_desktop_url")
    image_mobile_url = models.CharField(max_length=500, null=True, blank=True, db_column="image_mobile_url")
    image_alt = models.CharField(max_length=160, null=True, blank=True, db_column="image_alt")
    sort_order = models.IntegerField(default=0, db_column="sort_order")
    is_enabled = models.BooleanField(default=True, db_column="is_enabled")

    class Meta:
        db_table = "store_campaign_placement"
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["campaign", "slot"], name="placement_campaign_slot_idx"),
            models.Index(fields=["slot", "is_enabled"], name="placement_slot_enabled_idx"),
        ]

    def __str__(self):
        return f"{self.campaign_id}:{self.slot}"


class CampaignProduct(BaseModel):
    """Explicit product MID scope for a campaign landing (P4)."""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="products",
        db_column="campaign_id",
    )
    product_mid = models.CharField(max_length=64, db_column="product_mid", db_index=True)
    sort_order = models.IntegerField(default=0, db_column="sort_order")

    class Meta:
        db_table = "store_campaign_product"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "product_mid"],
                name="campaign_product_mid_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "sort_order"], name="campaign_product_sort_idx"),
        ]

    def __str__(self):
        return f"{self.campaign_id}:{self.product_mid}"


class CampaignCategory(BaseModel):
    """Category slug scope for a campaign landing (P4)."""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="categories",
        db_column="campaign_id",
    )
    category_slug = models.CharField(max_length=120, db_column="category_slug", db_index=True)
    sort_order = models.IntegerField(default=0, db_column="sort_order")

    class Meta:
        db_table = "store_campaign_category"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "category_slug"],
                name="campaign_category_slug_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "sort_order"], name="campaign_category_sort_idx"),
        ]

    def __str__(self):
        return f"{self.campaign_id}:{self.category_slug}"


class CampaignVoucher(BaseModel):
    """Link existing store vouchers for merchandising display (P5). No discount math here."""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="voucher_links",
        db_column="campaign_id",
    )
    voucher = models.ForeignKey(
        "storeApp.Voucher",
        on_delete=models.PROTECT,
        related_name="campaign_links",
        db_column="voucher_id",
    )
    sort_order = models.IntegerField(default=0, db_column="sort_order")
    is_featured = models.BooleanField(default=True, db_column="is_featured")

    class Meta:
        db_table = "store_campaign_voucher"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "voucher"],
                name="campaign_voucher_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "sort_order"], name="campaign_voucher_sort_idx"),
        ]

    def __str__(self):
        return f"{self.campaign_id}:voucher:{self.voucher_id}"


class ProductUnitPromotion(BaseModel):
    """
    Snapshot of a catalog tier promotion on one sale unit (P1 / D-PRC).
    Enables revert to previous_price_value + previous_compare_at_price.
    """

    SOURCE_HOT_SALE = "hot_sale"
    SOURCE_CMS = "cms"
    SOURCE_FLASH_SALE = "flash_sale"

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="unit_promotions",
        db_column="campaign_id",
    )
    product_variant_unit = models.ForeignKey(
        "storeApp.ProductVariantUnit",
        on_delete=models.CASCADE,
        related_name="promotions",
        db_column="product_variant_unit_id",
    )
    source = models.CharField(max_length=32, default=SOURCE_HOT_SALE, db_column="source")
    tier_percent = models.PositiveSmallIntegerField(db_column="tier_percent")
    list_price = models.DecimalField(max_digits=12, decimal_places=2, db_column="list_price")
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, db_column="sale_price")
    previous_price_value = models.DecimalField(max_digits=12, decimal_places=2, db_column="previous_price_value")
    previous_compare_at_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, db_column="previous_compare_at_price"
    )
    starts_at = models.DateTimeField(null=True, blank=True, db_column="starts_at")
    ends_at = models.DateTimeField(null=True, blank=True, db_column="ends_at")
    is_active = models.BooleanField(default=True, db_column="is_active", db_index=True)

    class Meta:
        db_table = "store_product_unit_promotion"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["campaign", "is_active"], name="unit_promo_campaign_active_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "product_variant_unit"],
                name="unit_promo_campaign_unit_unique",
            ),
        ]

    def __str__(self):
        return f"promo:{self.campaign_id}:unit:{self.product_variant_unit_id}:{self.tier_percent}%"
