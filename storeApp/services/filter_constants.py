"""
Filter Constants for Dynamic Filters Service
Contains all configuration and constants for filter building
"""
from django.conf import settings

# Cache configuration
CACHE_TIMEOUT = getattr(settings, 'DYNAMIC_FILTERS_CACHE_TTL', 3600)  # 1 hour
CACHE_PREFIX = 'dynamic_filters'

# Large category optimization
LARGE_CATEGORY_THRESHOLD = getattr(settings, 'LARGE_CATEGORY_THRESHOLD', 1000)  # Show subcategories only if > this
SUBCATEGORY_LEVEL_DEPTH = 1  # Get immediate children only (level + 1)

# Filter configuration
FILTER_CONFIGS = {
    'country': {
        'field': 'country',
        'label': 'Nước sản xuất',
        'type': 'checkbox',
        'searchable': True,
        'limit': 20
    },
    'brand': {
        'field': 'brand',
        'label': 'Thương hiệu',
        'type': 'checkbox',
        'searchable': True,
        'limit': 20
    },
    'priceRange': {
        'field': 'price_value',
        'label': 'Giá bán',
        'type': 'checkbox',
        'searchable': False,
        'limit': None
    },
    'targetAudience': {
        'field': 'targetAudience',
        'label': 'Đối tượng sử dụng',
        'type': 'checkbox',
        'searchable': True,
        'limit': 20
    },
    'flavor': {
        'field': 'flavor',
        'label': 'Mùi vị/Mùi hương',
        'type': 'checkbox',
        'searchable': True,
        'limit': 20
    },
    'indication': {
        'field': 'indication',
        'label': 'Chỉ định',
        'type': 'checkbox',
        'searchable': True,
        'limit': 20
    },
    'skinType': {
        'field': 'skinType',
        'label': 'Loại da',
        'type': 'checkbox',
        'searchable': True,
        'limit': 10
    },
    'medicineType': {
        'field': 'medicineType',
        'label': 'Loại thuốc',
        'type': 'checkbox',
        'searchable': True,
        'limit': 20
    },
    'ingredients': {
        'field': 'ingredients',
        'label': 'Thành phần',
        'type': 'checkbox',
        'searchable': True,
        'limit': 30
    }
}

# Price range configuration
PRICE_RANGES = {
    'under_100k': {
        'label': 'Dưới 100.000₫',
        'min': 0,
        'max': 100000
    },
    '100k_to_300k': {
        'label': '100.000₫ - 300.000₫',
        'min': 100000,
        'max': 300000
    },
    '300k_to_500k': {
        'label': '300.000₫ - 500.000₫',
        'min': 300000,
        'max': 500000
    },
    'over_500k': {
        'label': 'Trên 500.000₫',
        'min': 500000,
        'max': None
    }
}

# Category Type Filter Configuration - Map category type to enabled filters
CATEGORY_TYPE_FILTER_CONFIGS = {
    'medicine': {
        'enabled_filters': [
            'priceRange', 'brand', 'country',
            'targetAudience', 'indication', 'medicineType', 'ingredients'
        ],
        'filter_priority': [
            'priceRange', 'medicineType', 'brand', 'indication',
            'ingredients', 'targetAudience', 'country'
        ]
    },
    'cosmetics': {
        'enabled_filters': [
            'priceRange', 'brand', 'country',
            'targetAudience', 'indication', 'skinType'
        ],
        'filter_priority': [
            'priceRange', 'skinType', 'brand', 'targetAudience',
            'country', 'indication'
        ]
    },
    'supplements': {
        'enabled_filters': [
            'priceRange', 'brand', 'country',
            'targetAudience', 'indication', 'flavor'
        ],
        'filter_priority': [
            'priceRange', 'brand', 'country', 'targetAudience',
            'flavor', 'indication'
        ]
    }
}

# Default filter configuration (fallback for categories without specific config)
DEFAULT_FILTER_CONFIG = {
    'enabled_filters': [
        'priceRange', 'brand', 'country',
        'targetAudience', 'indication', 'flavor'
    ],
    'filter_priority': [
        'priceRange', 'brand', 'country', 'targetAudience',
        'flavor', 'indication'
    ]
}

# Filter ID to variant key mapping
FILTER_VARIANT_MAP = {
    'country': 'countries',
    'brand': 'brands',
    'priceRange': 'priceRanges',
    'targetAudience': 'targetAudiences',
    'flavor': 'flavors',
    'indication': 'indications',
    # Future filters
    'skinType': 'skinTypes',
    'medicineType': 'medicineTypes',
    'ingredients': 'ingredients'
}

# Target audience extraction patterns
TARGET_AUDIENCE_PATTERNS = {
    'trẻ em': ['trẻ em', 'trẻ nhỏ', 'trẻ sơ sinh', 'trẻ từ', 'cho trẻ'],
    'người lớn': ['người lớn', 'người trưởng thành', 'người từ 18 tuổi'],
    'phụ nữ': ['phụ nữ', 'chị em', 'phụ nữ mang thai', 'phụ nữ cho con bú'],
    'người cao tuổi': ['người cao tuổi', 'người già', 'người lớn tuổi'],
    'nam giới': ['nam giới', 'đàn ông', 'nam'],
    'phụ nữ mang thai': ['phụ nữ mang thai', 'bà bầu', 'thai phụ'],
    'phụ nữ cho con bú': ['phụ nữ cho con bú', 'mẹ cho con bú', 'đang cho con bú']
}

# Indication keywords for extraction
INDICATION_KEYWORDS = {
    'Cảm cúm': ['cảm cúm', 'cảm lạnh', 'sốt', 'ho', 'sổ mũi'],
    'Đau đầu': ['đau đầu', 'nhức đầu', 'migraine'],
    'Đau bụng': ['đau bụng', 'đau dạ dày', 'rối loạn tiêu hóa'],
    'Viêm họng': ['viêm họng', 'đau họng', 'sưng họng'],
    'Ho': ['ho', 'ho khan', 'ho có đờm'],
    'Sốt': ['sốt', 'hạ sốt', 'giảm sốt'],
    'Đau khớp': ['đau khớp', 'viêm khớp', 'thấp khớp'],
    'Mất ngủ': ['mất ngủ', 'khó ngủ', 'rối loạn giấc ngủ'],
    'Tăng cường miễn dịch': ['tăng cường miễn dịch', 'nâng cao sức đề kháng', 'hỗ trợ miễn dịch'],
    'Bổ sung vitamin': ['bổ sung vitamin', 'thiếu vitamin', 'vitamin'],
    'Bổ sung canxi': ['bổ sung canxi', 'thiếu canxi', 'canxi'],
    'Giảm stress': ['giảm stress', 'giảm căng thẳng', 'stress'],
    'Hỗ trợ tiêu hóa': ['hỗ trợ tiêu hóa', 'tiêu hóa', 'rối loạn tiêu hóa']
}

# Specification keys for extraction
SPECIFICATION_KEYS = {
    'targetAudience': ['targetAudience', 'target_audience', 'audience', 'target', 'for'],
    'flavor': ['flavor', 'flavour', 'taste', 'mùi vị', 'mùi hương', 'hương vị'],
    'skinType': ['skinType', 'skin_type', 'loại da', 'skin'],
    'ingredients': ['ingredients', 'ingredient', 'thành phần', 'active_ingredient']
}

# Skin type patterns
SKIN_TYPE_PATTERNS = {
    'Da dầu': ['da dầu', 'dầu', 'oily skin', 'sebum'],
    'Da khô': ['da khô', 'khô', 'dry skin'],
    'Da hỗn hợp': ['da hỗn hợp', 'hỗn hợp', 'combination skin'],
    'Da nhạy cảm': ['da nhạy cảm', 'nhạy cảm', 'sensitive skin'],
    'Da thường': ['da thường', 'normal skin']
}

# Medicine type patterns
MEDICINE_TYPE_PATTERNS = {
    'Thuốc kê đơn': ['kê đơn', 'prescription', 'theo đơn'],
    'Thuốc không kê đơn': ['không kê đơn', 'otc', 'over the counter'],
    'Thuốc bổ': ['thuốc bổ', 'bổ sung', 'supplement'],
    'Thuốc kháng sinh': ['kháng sinh', 'antibiotic'],
    'Thuốc giảm đau': ['giảm đau', 'pain relief', 'analgesic']
}

# Ingredient keywords (common active ingredients)
INGREDIENT_KEYWORDS = [
    'paracetamol', 'acetaminophen', 'ibuprofen', 'aspirin',
    'cetirizine', 'loratadine', 'diphenhydramine',
    'amoxicillin', 'azithromycin', 'penicillin',
    'vitamin c', 'vitamin d', 'calcium', 'iron', 'zinc'
]

# Category type mapping - Map root slug patterns to category types
CATEGORY_TYPE_MAPPING = {
    'thuoc': 'medicine',
    'duoc-mi-pham': 'cosmetics',
    'cosmetics': 'cosmetics',
    'thuc-pham-chuc-nang': 'supplements',
    'supplements': 'supplements'
}
