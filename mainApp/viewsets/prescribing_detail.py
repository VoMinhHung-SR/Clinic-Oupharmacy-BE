from rest_framework import viewsets, generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework import status

from mainApp.models import PrescriptionDetail
from mainApp.serializers import PrescriptionDetailCRUDSerializer
from storeApp.services.stock import get_available_stock, deduct_stock
from storeApp.models import Product, ProductVariant, ProductVariantUnit


def _resolve_store_variant_from_medicine_unit(medicine_unit):
    """Best-effort mapping legacy medicine_unit -> store product variant."""
    if not medicine_unit or not getattr(medicine_unit, "medicine", None):
        return None

    medicine = medicine_unit.medicine
    product = None
    if medicine.mid:
        product = Product.objects.using("store").filter(mid=medicine.mid).first()
    if not product and medicine.slug:
        product = Product.objects.using("store").filter(slug=medicine.slug).first()
    if not product and medicine.name:
        product = Product.objects.using("store").filter(name=medicine.name).first()
    if not product:
        return None

    variant = None
    if medicine_unit.package_size:
        variant = ProductVariant.objects.using("store").filter(
            product_id=product.id,
            packing=medicine_unit.package_size,
            active=True,
        ).first()
    if not variant:
        variant = ProductVariant.objects.using("store").filter(product_id=product.id, active=True).first()
    return variant

class PrescriptionDetailViewSet(viewsets.ViewSet, generics.RetrieveAPIView,
                                generics.UpdateAPIView, generics.CreateAPIView, generics.DestroyAPIView):
    queryset = PrescriptionDetail.objects.filter(active=True)
    serializer_class = PrescriptionDetailCRUDSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def get_parsers(self):
        return super().get_parsers()

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            medicine_unit = serializer.validated_data['medicine_unit']
            quantity = serializer.validated_data['quantity']
            variant = _resolve_store_variant_from_medicine_unit(medicine_unit)
            if not variant:
                return Response(
                    {"message": "Medicine unit is not mapped to store product variant"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            pvu = ProductVariantUnit.objects.using("store").filter(
                variant_id=variant.id,
                is_default=True,
                is_published=True,
            ).first() or ProductVariantUnit.objects.using("store").filter(
                variant_id=variant.id,
                is_published=True,
            ).order_by("unit_order", "id").first()

            quantity_in_base = pvu.quantity_in_base if pvu else 1
            required_base_quantity = int(quantity) * int(quantity_in_base)

            available = get_available_stock(variant.id)
            if available < required_base_quantity:
                return Response(
                    {"message": "Medicine quantity over the stock"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            deduct_stock(variant.id, required_base_quantity)
            self.perform_create(serializer)

            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

        except ValueError as ve:
            return Response(
                {"message": str(ve) or "Medicine quantity over the stock"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValidationError as ve:
            return Response(
                {"message": ve.detail},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            return Response(
                {"message": "Server Error. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )