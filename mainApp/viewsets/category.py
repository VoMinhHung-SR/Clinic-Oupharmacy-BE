from storeApp.viewsets.category import CategoryViewSet as StoreCategoryViewSet


class CategoryViewSet(StoreCategoryViewSet):
    """
    Proxy categories from storeApp so we can drop legacy mainApp Category/Medicine tables.
    """
    pass
