from django.db.models import Case, When, Value, FloatField, Q
from mainApp.models import MedicineUnit


def get_top5_medicine_units_for_category(category):
    """
    Get Top 5 MedicineUnit for a level1 category
    Apply ranking_score heuristic
    """

    qs = MedicineUnit.objects.filter(
        Q(category=category) | Q(category__parent=category),
        is_published=True,
        in_stock__gt=0,
    )

    # ------------------------
    # Ranking score components
    # ------------------------
    qs = qs.annotate(
        sold_score=Case(
            When(product_ranking__gte=100, then=Value(100)),
            default="product_ranking",
            output_field=FloatField(),
        ),

        hot_score=Case(
            When(is_hot=True, then=Value(100)),
            default=Value(0),
            output_field=FloatField(),
        ),

        discount_score=Case(
            # >= 15%
            When(
                original_price_value__isnull=False,
                original_price_value__gt=0,
                price_value__lt=F("original_price_value") * 0.85,
                then=Value(100),
            ),
            # 5–15%
            When(
                original_price_value__isnull=False,
                original_price_value__gt=0,
                price_value__lt=F("original_price_value") * 0.95,
                then=Value(50),
            ),
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
        qs.select_related("medicine")
          .order_by("-ranking_score", "-product_ranking")
          [:5]
    )
