from storeApp.viewsets.product import ProductViewSet


class MedicineViewSet(ProductViewSet):
    """
    Backward-compatible alias for legacy /medicines endpoint.
    Runtime data source is storeApp ProductVariant instead of mainApp Medicine.
    """