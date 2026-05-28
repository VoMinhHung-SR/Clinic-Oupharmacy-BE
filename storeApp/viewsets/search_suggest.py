from django.db.models import Case, Count, F, IntegerField, Prefetch, Q, Value, When
from django.db.models.functions import Lower
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from storeApp.models import Category, ProductVariant, ProductVariantUnit, SearchKeyword
from storeApp.services.variant_listing import one_variant_per_product

DEFAULT_KEYWORD_LIMIT = 5
DEFAULT_CATEGORY_LIMIT = 5
DEFAULT_PRODUCT_LIMIT = 5


def _get_default_unit(variant):
    units = getattr(variant, "prefetched_units", None)
    if units is None:
        units = list(getattr(variant, "units", []).all())
    for unit in units:
        if unit.is_default and unit.is_published:
            return unit
    for unit in units:
        if unit.is_published:
            return unit
    return None


def _get_variant_image_url(variant):
    if variant.image:
        try:
            from mainApp import cloud_context

            return f"{cloud_context}{variant.image}"
        except Exception:
            return None
    images = variant.images or []
    if images and isinstance(images, list):
        first = images[0]
        if isinstance(first, str):
            if first.startswith("http"):
                return first
            try:
                from mainApp import cloud_context

                return f"{cloud_context}{first}"
            except Exception:
                return None
        if isinstance(first, dict):
            return first.get("url")
    return None


class SearchSuggestViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        query = request.query_params.get("q", "")
        display_query = SearchKeyword.normalize_keyword(query)
        lookup_query = display_query.casefold()
        if not lookup_query:
            return Response(
                {
                    "query": display_query,
                    "suggestions": {
                        "history_search": [],
                        "hot_search": [],
                        "categories": [],
                        "top_products": [],
                    },
                    "meta": {"has_more": False, "source": "store", "took_ms": 0},
                },
                status=status.HTTP_200_OK,
            )

        keyword_qs = SearchKeyword.objects.filter(keyword_lookup__contains=lookup_query)

        history_qs = keyword_qs.order_by("-last_searched_at")[:DEFAULT_KEYWORD_LIMIT]
        hot_qs = keyword_qs.order_by("-hit_count", "-last_searched_at")[:DEFAULT_KEYWORD_LIMIT]

        category_qs = (
            Category.objects.filter(active=True)
            .annotate(name_lookup=Lower("name"), path_lookup=Lower("path"))
            .filter(Q(name_lookup__contains=lookup_query) | Q(path_lookup__contains=lookup_query))
            .annotate(product_count=Count("products", distinct=True))
            .order_by("-product_count", "name")[:DEFAULT_CATEGORY_LIMIT]
        )

        variants_qs = (
            ProductVariant.objects.filter(is_published=True, product__active=True)
            .select_related("product")
            .prefetch_related(
                Prefetch("units", queryset=ProductVariantUnit.objects.filter(is_published=True), to_attr="prefetched_units")
            )
            .annotate(
                product_name_lookup=Lower("product__name"),
                web_name_lookup=Lower("product__web_name"),
                match_score=Case(
                    When(product_name_lookup=lookup_query, then=Value(100)),
                    When(web_name_lookup=lookup_query, then=Value(95)),
                    When(product_name_lookup__startswith=lookup_query, then=Value(80)),
                    When(web_name_lookup__startswith=lookup_query, then=Value(75)),
                    When(product_name_lookup__contains=lookup_query, then=Value(60)),
                    When(web_name_lookup__contains=lookup_query, then=Value(55)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .filter(match_score__gt=0)
        )
        dedupe_order = [
            F("product_id").asc(),
            F("match_score").desc(),
            F("product_ranking").desc(),
            F("in_stock").desc(),
            F("id").asc(),
        ]
        variants_qs = one_variant_per_product(variants_qs, partition_order=dedupe_order).order_by(
            "-match_score", "-product_ranking", "-in_stock", "id"
        )[:DEFAULT_PRODUCT_LIMIT]

        top_products = []
        for variant in variants_qs:
            default_unit = _get_default_unit(variant)
            top_products.append(
                {
                    "variant_id": variant.id,
                    "product_name": variant.product.web_name or variant.product.name,
                    "packing": variant.packing,
                    "image": _get_variant_image_url(variant),
                    "price_display": (
                        default_unit.price_display
                        if default_unit and default_unit.price_display
                        else (str(default_unit.price_value) if default_unit and default_unit.price_value is not None else None)
                    ),
                    "match_score": variant.match_score,
                }
            )

        return Response(
            {
                "query": display_query,
                "suggestions": {
                    "history_search": [
                        {"keyword": kw.keyword, "last_searched_at": kw.last_searched_at} for kw in history_qs
                    ],
                    "hot_search": [{"keyword": kw.keyword, "hit_count": kw.hit_count} for kw in hot_qs],
                    "categories": [
                        {
                            "id": cat.id,
                            "name": cat.name,
                            "slug": cat.slug,
                            "path": cat.path,
                            "product_count": cat.product_count,
                        }
                        for cat in category_qs
                    ],
                    "top_products": top_products,
                },
                "meta": {"has_more": False, "source": "store", "took_ms": 0},
            },
            status=status.HTTP_200_OK,
        )
