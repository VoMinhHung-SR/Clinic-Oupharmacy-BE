from decimal import Decimal

from rest_framework import viewsets, generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework import status

from mainApp.models import PrescriptionDetail
from mainApp.serializers import PrescriptionDetailCRUDSerializer
from storeApp.services.stock import get_available_stock, deduct_stock
from storeApp.models import Product, ProductVariant, ProductVariantUnit


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

            quantity = serializer.validated_data["quantity"]
            product_variant_id = serializer.validated_data.get("product_variant_id")
            product_variant_unit_id = serializer.validated_data.get("product_variant_unit_id")

            if not product_variant_id and not product_variant_unit_id:
                return Response(
                    {"message": "Missing store identifiers. Provide product_variant_id or product_variant_unit_id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            variant = None
            pvu = None

            # Prefer using product_variant_unit_id if provided (less guessing).
            if product_variant_unit_id:
                pvu = (
                    ProductVariantUnit.objects.using("store")
                    .filter(id=product_variant_unit_id, is_published=True)
                    .first()
                )
                if not pvu:
                    return Response(
                        {"message": "product_variant_unit_id is not found (or not published) on store."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                variant = pvu.variant

            if not variant and product_variant_id:
                variant = ProductVariant.objects.using("store").filter(id=product_variant_id, active=True).first()
                if not variant:
                    return Response(
                        {"message": "product_variant_id is not found (or inactive) on store."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            if not pvu and variant:
                # Pick default published unit, fallback to any published unit.
                pvu = (
                    ProductVariantUnit.objects.using("store")
                    .filter(variant_id=variant.id, is_default=True, is_published=True)
                    .first()
                ) or ProductVariantUnit.objects.using("store").filter(
                    variant_id=variant.id,
                    is_published=True,
                ).order_by("unit_order", "id").first()

            if not variant:
                return Response(
                    {"message": "Cannot resolve store ProductVariant."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            quantity_in_base = pvu.quantity_in_base if pvu else 1
            required_base_quantity = int(quantity) * int(quantity_in_base)

            available = get_available_stock(variant.id)
            if available < required_base_quantity:
                return Response(
                    {"message": "Medicine quantity over the stock"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            deduct_stock(variant.id, required_base_quantity)
            serializer.save(
                product_id=variant.product_id,
                product_variant_id=variant.id,
                product_variant_unit_id=(pvu.id if pvu else None),
                item_name_snapshot=(variant.product.web_name or variant.product.name),
                unit_name_snapshot=(pvu.unit_name if pvu else (variant.packing or "")),
                unit_price_snapshot=(Decimal(str(pvu.price_value)) if pvu else Decimal("0")),
                quantity_in_base_snapshot=int(quantity_in_base),
            )

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