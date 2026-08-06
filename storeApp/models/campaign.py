"""Campaign + CampaignPlacement models (P1). Scope/voucher/order attribution land in later phases."""

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
    SLOT_HOME_HERO = "HOME_HERO"
    SLOT_HOME_PROMO_LEFT = "HOME_PROMO_LEFT"
    SLOT_HOME_PROMO_RIGHT = "HOME_PROMO_RIGHT"
    SLOT_HOME_STRIP = "HOME_STRIP"
    SLOT_CATEGORY_BANNER = "CATEGORY_BANNER"
    SLOT_SEARCH_BANNER = "SEARCH_BANNER"
    SLOT_CHOICES = [
        (SLOT_HOME_HERO, "Home hero"),
        (SLOT_HOME_PROMO_LEFT, "Home promo left"),
        (SLOT_HOME_PROMO_RIGHT, "Home promo right"),
        (SLOT_HOME_STRIP, "Home strip"),
        (SLOT_CATEGORY_BANNER, "Category banner"),
        (SLOT_SEARCH_BANNER, "Search banner"),
    ]

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
