from django.db.models import Case, FloatField, F, Value, When

from storeApp.models import ProductVariant
from storeApp.services.product_category_helpers import category_tree_ids, product_in_categories_exists


def get_top5_medicine_units_for_category(category):
    """
    Get Top 5 ProductVariant for a level1 category subtree (ProductCategory M2M).
    Apply ranking_score heuristic.
    """
    category_ids = category_tree_ids(category)

    qs = ProductVariant.objects.filter(
        is_published=True,
        in_stock__gt=0,
    ).filter(product_in_categories_exists(category_ids))

    qs = qs.annotate(
        sold_score=Case(
            When(product_ranking__gte=100, then=Value(100.0)),
            default=F("product_ranking"),
            output_field=FloatField(),
        ),
        hot_score=Case(
            When(is_hot=True, then=Value(100)),
            default=Value(0),
            output_field=FloatField(),
        ),
        discount_score=Case(
            default=Value(0),
            output_field=FloatField(),
        ),
        stock_score=Case(
            When(in_stock__gt=10, then=Value(100)),
            When(in_stock__gt=0, then=Value(50)),
            default=Value(0),
            output_field=FloatField(),
        ),
    )

    qs = qs.annotate(
        ranking_score=(
            F("sold_score") * 0.5
            + F("hot_score") * 0.2
            + F("discount_score") * 0.2
            + F("stock_score") * 0.1
        )
    )

    return (
        qs.select_related("product")
        .order_by("-ranking_score", "-product_ranking")[:5]
    )
