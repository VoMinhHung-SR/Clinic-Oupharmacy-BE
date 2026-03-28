from storeApp.viewsets.product import ProductViewSet


class MedicineUnitViewSet(ProductViewSet):
    """
    Backward-compatible alias for legacy /medicine-units endpoint.
    Serves storeApp ProductVariant data to avoid mainApp MedicineUnit dependency.
    """