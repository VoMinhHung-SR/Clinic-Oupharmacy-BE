"""Filterable catalog attributes attached to Product (facet sidebar)."""

from django.db import models

from mainApp.models import BaseModel


class CatalogAttribute(BaseModel):
    """Attribute definition shown as a sidebar facet group when products have values."""

    FACET_MULTIPLE = "multiple"
    FACET_SINGLE = "single"
    FACET_TYPE_CHOICES = (
        (FACET_MULTIPLE, "Multiple"),
        (FACET_SINGLE, "Single"),
    )

    code = models.SlugField(
        max_length=64,
        unique=True,
        db_column="code",
        help_text="Stable key used in attrs= query params (e.g. skin_type).",
    )
    label = models.CharField(max_length=120, db_column="label")
    facet_type = models.CharField(
        max_length=16,
        choices=FACET_TYPE_CHOICES,
        default=FACET_MULTIPLE,
        db_column="facet_type",
    )
    sort_order = models.PositiveIntegerField(default=100, db_column="sort_order")
    is_filterable = models.BooleanField(default=True, db_column="is_filterable")

    class Meta:
        db_table = "store_catalog_attribute"
        ordering = ["sort_order", "code"]
        indexes = [
            models.Index(fields=["is_filterable", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.code} ({self.label})"


class CatalogAttributeOption(BaseModel):
    """Allowed value for a CatalogAttribute."""

    attribute = models.ForeignKey(
        CatalogAttribute,
        on_delete=models.CASCADE,
        related_name="options",
        db_column="attribute_id",
    )
    slug = models.SlugField(max_length=120, db_column="slug")
    label = models.CharField(max_length=160, db_column="label")
    sort_order = models.PositiveIntegerField(default=100, db_column="sort_order")

    class Meta:
        db_table = "store_catalog_attribute_option"
        ordering = ["sort_order", "slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["attribute", "slug"],
                name="uniq_store_attr_option_attr_slug",
            ),
        ]
        indexes = [
            models.Index(fields=["attribute", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.attribute.code}:{self.slug}"


class ProductAttributeValue(BaseModel):
    """Product ↔ attribute option assignment (product-level, not variant)."""

    product = models.ForeignKey(
        "storeApp.Product",
        on_delete=models.CASCADE,
        related_name="attribute_values",
        db_column="product_id",
    )
    option = models.ForeignKey(
        CatalogAttributeOption,
        on_delete=models.CASCADE,
        related_name="product_values",
        db_column="option_id",
    )

    class Meta:
        db_table = "store_product_attribute_value"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "option"],
                name="uniq_store_pav_product_option",
            ),
        ]
        indexes = [
            models.Index(fields=["option", "product"]),
        ]

    def __str__(self):
        return f"{self.product_id}:{self.option_id}"
