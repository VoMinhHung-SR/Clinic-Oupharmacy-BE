from rest_framework import viewsets, generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework import status

from mainApp.models import PrescriptionDetail
from mainApp.serializers import PrescriptionDetailCRUDSerializer
from storeApp.services.stock import get_available_stock, deduct_stock

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
            medicine_unit_id = medicine_unit.id

            available = get_available_stock(medicine_unit_id)
            if available < quantity:
                return Response(
                    {"message": "Medicine quantity over the stock"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            deduct_stock(medicine_unit_id, quantity)
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