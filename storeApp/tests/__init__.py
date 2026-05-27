"""
storeApp tests package — modules are split by feature (`test_*.py`).

Django discovers `test*.py` under this package. Submodules are also imported
here so `from storeApp.tests import SearchApiTests` keeps working.
"""

from storeApp.tests.test_cart_checkout import (
    CartCheckoutDeliveryApiTests,
    FreeShippingThresholdTests,
    GuestCartCheckoutTests,
    StoreConstantsUnitTests,
)
from storeApp.tests.test_cart_versioning import (
    CartCurrentCacheReadThroughTests,
    CartVersioningFlowTests,
)
from storeApp.tests.test_category_m2m_api import ProductsByCategoryM2MAPITests
from storeApp.tests.test_checkout_delivery_resolve import CheckoutDeliveryResolveTests
from storeApp.tests.test_import_catalog import (
    StoreImportCategoryMergeTests,
    StoreImportCsvHelperTests,
)
from storeApp.tests.test_order_voucher import OrderVoucherCreateTests
from storeApp.tests.test_search import (
    SearchApiTests,
    SearchKeywordApiTests,
    SearchSuggestApiTests,
)

__all__ = [
    "CartCheckoutDeliveryApiTests",
    "CartCurrentCacheReadThroughTests",
    "CartVersioningFlowTests",
    "CheckoutDeliveryResolveTests",
    "FreeShippingThresholdTests",
    "GuestCartCheckoutTests",
    "OrderVoucherCreateTests",
    "ProductsByCategoryM2MAPITests",
    "SearchApiTests",
    "SearchKeywordApiTests",
    "SearchSuggestApiTests",
    "StoreConstantsUnitTests",
    "StoreImportCategoryMergeTests",
    "StoreImportCsvHelperTests",
]
