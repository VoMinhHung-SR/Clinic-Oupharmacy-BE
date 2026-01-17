"""
Filter Helper Utilities
Helper methods for category, queryset, and data retrieval
"""
from collections import defaultdict
from django.db import models
from django.db.models import Q
from django.db.models import Count
from mainApp.models import Category, MedicineUnit
from storeApp.models import Brand
from storeApp.services.filter_constants import (
    FILTER_VARIANT_MAP,
    CATEGORY_TYPE_MAPPING,
    SUBCATEGORY_LEVEL_DEPTH
)


class FilterHelpers:
    """Helper utilities for dynamic filters"""
    
    @staticmethod
    def get_category_from_slug(category_slug: str):
        """Get category from slug"""
        return Category.objects.using('default').filter(
            active=True
        ).filter(
            models.Q(path_slug__iexact=category_slug) | 
            models.Q(slug__iexact=category_slug)
        ).first()
    
    @staticmethod
    def get_root_category(category_slug: str = None, category=None):
        """
        Lấy root category (level = 0) từ database
        
        Args:
            category_slug: Category slug (optional)
            category: Category object (optional)
        
        Returns:
            Category: Root category object hoặc None
        """
        root_slug = None
        
        # Nếu đã có category object
        if category:
            # Nếu đã là root category (level = 0), return luôn
            if category.level == 0:
                return category
            
            # Lấy root slug từ path_slug (nhanh nhất, không cần query thêm)
            if category.path_slug:
                root_slug = category.path_slug.split('/')[0]
            elif category.slug:
                root_slug = category.slug
        
        # Nếu chỉ có category_slug, lấy root slug từ đó
        elif category_slug:
            root_slug = category_slug.split('/')[0]
        
        # Query root category từ database (level = 0, parent = None)
        if root_slug:
            return Category.objects.using('default').filter(
                active=True,
                level=0,
                parent__isnull=True,
                slug=root_slug
            ).first()
        
        return None
    
    @staticmethod
    def get_category_type_from_root_slug(root_slug: str):
        """
        Map root category slug sang category type
        Logic: Dựa vào CATEGORY_TYPE_MAPPING để xác định type
        """
        if not root_slug:
            return 'default'
        
        slug_lower = root_slug.lower()
        
        # Check exact match first
        if slug_lower in CATEGORY_TYPE_MAPPING:
            return CATEGORY_TYPE_MAPPING[slug_lower]
        
        # Check partial match (for nested slugs)
        for pattern, category_type in CATEGORY_TYPE_MAPPING.items():
            if pattern in slug_lower:
                return category_type
        
        return 'default'
    
    @staticmethod
    def get_category_type(category_slug: str):
        """Xác định category type từ slug"""
        if not category_slug:
            return 'default'
        
        root_category = FilterHelpers.get_root_category(category_slug=category_slug)
        if not root_category:
            return 'default'
        
        return FilterHelpers.get_category_type_from_root_slug(root_category.slug)
    
    @staticmethod
    def get_category_type_from_category(category):
        """Xác định category type từ Category object"""
        if not category:
            return 'default'
        
        root_category = FilterHelpers.get_root_category(category=category)
        if not root_category:
            return 'default'
        
        return FilterHelpers.get_category_type_from_root_slug(root_category.slug)
    
    @staticmethod
    def has_variants(variants, filter_id):
        """Check xem filter có variants không"""
        variant_key = FILTER_VARIANT_MAP.get(filter_id)
        if not variant_key:
            return False
        return bool(variants.get(variant_key))
    
    @staticmethod
    def get_category_queryset(category):
        """Get MedicineUnit queryset for category (including subcategories)"""
        category_path_slug = category.path_slug or category.slug
        
        # Get all category IDs (including subcategories)
        category_ids = [category.id]
        subcategories = Category.objects.using('default').filter(
            active=True,
            path_slug__istartswith=f"{category_path_slug}/"
        ).values_list('id', flat=True)
        category_ids.extend(list(subcategories))
        
        # Get MedicineUnits in these categories
        return MedicineUnit.objects.using('default').filter(
            active=True,
            is_published=True,
            category_id__in=category_ids
        ).select_related('medicine', 'category')
    
    @staticmethod
    def get_brand_data(queryset):
        """
        Get brand IDs and brand data in one optimized query
        Returns: (brand_ids_list, brands_dict) where brands_dict maps brand_id -> (name, country)
        """
        brand_ids = queryset.exclude(
            Q(medicine__brand_id__isnull=True) | Q(medicine__brand_id=0)
        ).values_list('medicine__brand_id', flat=True).distinct()
        
        brand_ids_list = list(brand_ids)
        brands_dict = {}
        
        if brand_ids_list:
            # Get all brand data in single query
            brands_data = Brand.objects.using('store').filter(
                id__in=brand_ids_list,
                active=True
            ).values_list('id', 'name', 'country')
            
            brands_dict = {
                brand_id: (name, country)
                for brand_id, name, country in brands_data
            }
        
        return brand_ids_list, brands_dict
    
    @staticmethod
    def calculate_median(values):
        """Calculate median from values"""
        if not values:
            return 0
        values_list = sorted([v for v in values if v])
        n = len(values_list)
        if n == 0:
            return 0
        if n % 2 == 0:
            return (values_list[n//2 - 1] + values_list[n//2]) / 2
        return values_list[n//2]
    
    @staticmethod
    def generate_price_ranges(min_price, max_price):
        """Generate price range keys based on min/max prices"""
        ranges = []
        if min_price < 100000:
            ranges.append('under_100k')
        if min_price < 300000 or max_price >= 100000:
            ranges.append('100k_to_300k')
        if min_price < 500000 or max_price >= 300000:
            ranges.append('300k_to_500k')
        if max_price >= 500000:
            ranges.append('over_500k')
        return sorted(set(ranges))
    
    @staticmethod
    def get_immediate_subcategories(category):
        """
        Get immediate subcategories (children) of a category with product counts
        Returns list of subcategory dicts with slug, name, productCount, level
        
        Args:
            category: Category object
        
        Returns:
            list: List of subcategory dicts
        """
        if not category:
            return []
        
        # Get immediate children: level = category.level + 1
        category_path = category.path_slug or category.slug
        target_level = category.level + 1
        
        # Build parent path with trailing slash for matching
        parent_path_with_slash = category_path + '/'
        
        # Strategy 1: Query by parent relationship (most reliable)
        parent_subcategories = Category.objects.using('default').filter(
            active=True,
            parent=category
        )
        
        # Strategy 2: Query by level and path_slug (fallback)
        path_subcategories = Category.objects.using('default').filter(
            active=True,
            level=target_level,
            path_slug__istartswith=parent_path_with_slash
        )
        
        # Combine results and filter to only direct children
        seen_ids = set()
        result_list = []
        
        # Add from parent query (already direct children)
        for subcat in parent_subcategories:
            if subcat.id not in seen_ids:
                result_list.append(subcat)
                seen_ids.add(subcat.id)
        
        # Add from path_slug query (filter to direct children only)
        for subcat in path_subcategories:
            if subcat.id in seen_ids:
                continue
            
            subcat_path = subcat.path_slug or subcat.slug
            if not subcat_path or not subcat_path.startswith(parent_path_with_slash):
                continue
            
            # Get remaining part after parent_path/
            remaining = subcat_path[len(parent_path_with_slash):]
            
            # Direct child: remaining has no "/" (not a grandchild)
            if remaining and '/' not in remaining:
                result_list.append(subcat)
                seen_ids.add(subcat.id)
        
        immediate_subcategories = result_list
        
        if not immediate_subcategories:
            return []
        
        # Get product counts for each subcategory (optimized queries)
        subcategory_ids = [subcat.id for subcat in immediate_subcategories]
        subcategory_paths = {subcat.id: (subcat.path_slug or subcat.slug) for subcat in immediate_subcategories}
        
        # Get all nested subcategories and collect category IDs efficiently
        # Use set from start to avoid duplicates
        all_category_ids = set(subcategory_ids)
        
        if subcategory_paths:
            # Query nested subcategories for each immediate subcategory
            # Build mapping: subcategory_id -> [nested_ids]
            subcategory_with_children = {subcat_id: [subcat_id] for subcat_id in subcategory_ids}
            
            for subcat_id, subcat_path in subcategory_paths.items():
                nested_ids = list(Category.objects.using('default').filter(
                    active=True,
                    path_slug__istartswith=f"{subcat_path}/"
                ).values_list('id', flat=True))
                subcategory_with_children[subcat_id].extend(nested_ids)
                all_category_ids.update(nested_ids)
        else:
            subcategory_with_children = {subcat_id: [subcat_id] for subcat_id in subcategory_ids}
        
        # Convert to list for query
        all_category_ids = list(all_category_ids)
        
        # Single query for all product counts
        product_counts = MedicineUnit.objects.using('default').filter(
            active=True,
            is_published=True,
            category_id__in=all_category_ids
        ).values('category_id').annotate(count=Count('id'))
        
        # Build count map
        count_map = {item['category_id']: item['count'] for item in product_counts}
        
        # For each immediate subcategory, sum counts including nested
        result = []
        for subcat in immediate_subcategories:
            # Sum counts for this subcategory and all its children
            total_count = sum(
                count_map.get(cat_id, 0)
                for cat_id in subcategory_with_children.get(subcat.id, [subcat.id])
            )
            
            result.append({
                'slug': subcat.path_slug or subcat.slug,
                'name': subcat.path or subcat.name,
                'productCount': total_count,
                'level': subcat.level
            })
        
        # Sort by productCount descending, then by name
        result.sort(key=lambda x: (-x['productCount'], x['name']))
        
        return result