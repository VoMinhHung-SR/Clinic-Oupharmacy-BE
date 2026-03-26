from django.db.models import Case, When, Value, FloatField, Q, F
from storeApp.models import ProductVariant


def get_top5_medicine_units_for_category(category):
    """
    Get Top 5 ProductVariant for a level1 category
    Apply ranking_score heuristic
    """

    qs = ProductVariant.objects.filter(
        Q(product__category=category) | Q(product__category__parent=category),
        is_published=True,
        in_stock__gt=0,
    )

    # ------------------------
    # Ranking score components
    # ------------------------
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

    # ------------------------
    # Final ranking score
    # ------------------------
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
          .order_by("-ranking_score", "-product_ranking")
          [:5]
    )
