"""
Category navigation helpers (subcategories for resolve-path / listing).
"""
from django.conf import settings

from storeApp.models import Category
from storeApp.services.product_category_helpers import count_distinct_products_in_category_ids


class FilterHelpers:
    """Category listing navigation helpers."""

    STORE_DB_ALIAS = "store" if "store" in settings.DATABASES else "default"

    @staticmethod
    def get_immediate_subcategories(category):
        """
        Get immediate subcategories (children) of a category with product counts.
        Returns list of subcategory dicts with slug, name, productCount, level.
        """
        if not category:
            return []

        category_path = category.path_slug or category.slug
        target_level = category.level + 1
        parent_path_with_slash = category_path + "/"

        parent_subcategories = Category.objects.using(FilterHelpers.STORE_DB_ALIAS).filter(
            active=True,
            parent=category,
        )

        path_subcategories = Category.objects.using(FilterHelpers.STORE_DB_ALIAS).filter(
            active=True,
            level=target_level,
            path_slug__istartswith=parent_path_with_slash,
        )

        seen_ids = set()
        result_list = []

        for subcat in parent_subcategories:
            if subcat.id not in seen_ids:
                result_list.append(subcat)
                seen_ids.add(subcat.id)

        for subcat in path_subcategories:
            if subcat.id in seen_ids:
                continue

            subcat_path = subcat.path_slug or subcat.slug
            if not subcat_path or not subcat_path.startswith(parent_path_with_slash):
                continue

            remaining = subcat_path[len(parent_path_with_slash) :]
            if remaining and "/" not in remaining:
                result_list.append(subcat)
                seen_ids.add(subcat.id)

        if not result_list:
            return []

        subcategory_ids = [subcat.id for subcat in result_list]
        subcategory_paths = {
            subcat.id: (subcat.path_slug or subcat.slug) for subcat in result_list
        }

        subcategory_with_children = {subcat_id: [subcat_id] for subcat_id in subcategory_ids}
        descendants = list(
            Category.objects.using(FilterHelpers.STORE_DB_ALIAS)
            .filter(
                active=True,
                path_slug__istartswith=parent_path_with_slash,
                level__gt=target_level,
            )
            .values_list("id", "path_slug")
        )
        for descendant_id, descendant_path in descendants:
            if not descendant_path:
                continue
            for subcat_id, subcat_path in subcategory_paths.items():
                if descendant_path.startswith(f"{subcat_path}/"):
                    subcategory_with_children[subcat_id].append(descendant_id)
                    break

        result = []
        for subcat in result_list:
            tree_ids = subcategory_with_children.get(subcat.id, [subcat.id])
            total_count = count_distinct_products_in_category_ids(
                tree_ids, using=FilterHelpers.STORE_DB_ALIAS
            )
            result.append(
                {
                    "slug": subcat.path_slug or subcat.slug,
                    "name": subcat.path or subcat.name,
                    "productCount": total_count,
                    "level": subcat.level,
                }
            )

        result.sort(key=lambda x: (-x["productCount"], x["name"]))
        return result
