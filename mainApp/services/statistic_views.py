import datetime

from django.core.exceptions import ValidationError
from django.db.models.aggregates import Sum
from django.db.models.functions.datetime import TruncMonth
from django.db.models import Count, DateTimeField
from rest_framework.response import Response
from rest_framework import status
from rest_framework import permissions
from rest_framework.decorators import action, api_view, permission_classes

from mainApp.constant import ROLE_NURSE, ROLE_DOCTOR
from mainApp.models import CommonCity, UserRole, User, Category, Examination, PrescriptionDetail, Bill


@api_view(http_method_names=["POST"])
@permission_classes([permissions.IsAuthenticated])
def get_booking_stats(request):
    try:
        quarter = request.data.get('quarter', '0')
        year = request.data.get('year', '0')

        # Validate quarter and year
        try:
            quarter_number = int(quarter)
            year_number = int(year) if year != '0' else datetime.date.today().year
        except ValueError:
            return Response({"errMsg": "Invalid input for quarter or year."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Fetch and filter examinations
        examinations = Examination.objects.all()
        if quarter_number > 0:
            examinations = examinations.filter(created_date__quarter=quarter_number)
        examinations = examinations.filter(created_date__year=year_number)

        # Aggregate data by month
        examination_stats = (
            examinations
            .annotate(month=TruncMonth('created_date'))
            .values('month')
            .annotate(count=Count('pk'))
        )

        # Prepare data for chart
        data_examination = [0] * 12
        for stat in examination_stats:
            data_examination[stat['month'].month - 1] = stat['count']

        return Response(
            {
                "data_examination": data_examination,
                "title": f'Thống kê tần suất đặt lịch khám theo các tháng trong năm {year_number}',
            },
            status=status.HTTP_200_OK,
        )

    except Exception as ex:
        # Log the exception for debugging purposes
        print(f"Error in get_booking_stats: {ex}")
        return Response({"errMsg": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(http_method_names=["POST"])
@permission_classes([permissions.IsAuthenticated])
def get_medicines_stats(request):
    # if not request.user.is_staff:
    #     return Response({"error": "Forbidden"}, status=403)

    try:
        # Get query parameters
        quarter = request.data.get('quarter', '0')
        year = request.data.get('year', '0')

        # Parse and validate input
        quarter_number = int(quarter)
        year_number = int(year) if year != '0' else datetime.date.today().year

        if quarter_number not in range(0, 5):
            raise ValidationError("Invalid quarter. Quarter must be between 0 and 4.")

        # Query medicines
        medicines = PrescriptionDetail.objects.filter(
            created_date__year=year_number, active=True
        )

        if quarter_number > 0:
            medicines = medicines.filter(created_date__quarter=quarter_number)

        medicines = medicines.values('medicine_unit__medicine__name') \
            .annotate(count=Count('medicine_unit')) \
            .order_by('-count')  # Order by frequency, descending

        # Prepare data for the pie chart
        top_10 = medicines[:10]
        others_count = sum(m['count'] for m in medicines[10:])

        data_medicine_labels = [m['medicine_unit__medicine__name'] for m in top_10]
        data_medicine_quantity = [m['count'] for m in top_10]

        if others_count > 0:
            data_medicine_labels.append("Others")
            data_medicine_quantity.append(others_count)

        # Construct response
        return Response({
            "data_medicine_labels": data_medicine_labels,
            "data_medicine_quantity": data_medicine_quantity,
        })

    except ValidationError as ex:
        return Response({"error": str(ex)}, status=400)
    except Exception as ex:
        return Response({"error": "Server Error", "details": str(ex)}, status=500)

@api_view(http_method_names=["POST"])
@permission_classes([permissions.IsAuthenticated])
def get_revenue_stats(request):
    try:
        bills = Bill.objects.all()
        quarter = request.data.get('quarter', '0')
        year = request.data.get('year', '0')

        # Validate quarter and year
        try:
            quarter_number = int(quarter)
            year_number = int(year) if year != '0' else datetime.date.today().year
        except ValueError:
            return Response({"errMsg": "Invalid input for quarter or year."},
                            status=status.HTTP_400_BAD_REQUEST)

        if quarter_number > 0:
            bills = bills.filter(created_date__quarter=quarter_number)
        bills = bills.filter(created_date__year=year_number)

        bills = (
            bills.filter(created_date__year=year_number)
            .annotate(month=TruncMonth('created_date'))
            .values('month')
            .annotate(total=Sum("amount"), count=Count("id"))
            .values('month', 'total', 'count')
        )

        data_revenue = [0] * 12
        for record in bills:
            month_index = record['month'].month - 1
            data_revenue[month_index] = record['total']

        return Response({
            "data_revenue": data_revenue
        }, status=status.HTTP_200_OK)

    except ValueError:
        return Response({"errMsg": "Invalid input for quarter or year."}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as ex:
        return Response({"errMsg": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)