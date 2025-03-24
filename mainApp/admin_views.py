import random

from rest_framework.decorators import api_view

from rest_framework import status
from django.http import JsonResponse
from django.http import HttpResponseNotFound, HttpResponseForbidden, \
    HttpResponseBadRequest, HttpResponseServerError
from django.db.models import Count, Sum
from .models import *
from django.db.models.functions import TruncMonth
from datetime import date

colors = ['#2c3e50', '#3c8dbc', '#f39c12', '#f1c40f', '#d63031', '#f56954', '#e67e22',
          '#8e44ad',
          '#1abc9c',
          '#3498db',
          '#2ecc71',
          '#bdc3c7']


def get_admin_revenue(request):
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        bills = Bill.objects
        quarter_number = int(quarter)
        year_number = int(year)
        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            bills = bills.filter(created_date__quarter=quarter_number)

        bills = bills.filter(created_date__year=year_number) \
            .annotate(month=TruncMonth('created_date')) \
            .values('month').annotate(total=Sum("amount"), count=Count("id")).values('month', 'total', 'count')
        data_revenue = [0] * 12
        for rs in bills:
            month = rs['month'].month - 1
            data_revenue[month] = rs['total']

    except Exception as ex:
        return HttpResponseServerError({"errMgs": "value Error"})
    else:
        return JsonResponse({"data_revenue": data_revenue,
                             "title": f'Thống kê doanh thu theo các tháng trong năm {year_number}'})


def get_examinations_stats(request):
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        examinations = Examination.objects
        quarter_number = int(quarter)
        year_number = int(year)

        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            examinations = examinations.filter(created_date__quarter=quarter_number)

        # Get examination data
        examinations = examinations.filter(created_date__year=year_number) \
            .annotate(month=TruncMonth('created_date')) \
            .values('month').annotate(count=Count('pk')).values('month', 'count')

        # Prepare examination data for chart
        data_examination = [0] * 12
        for rs in examinations:
            month = rs['month'].month - 1
            data_examination[month] = rs['count']


    except Exception as ex:
        return HttpResponseServerError({"errMgs": "value Error"})
    else:
        return JsonResponse({"data_examination": data_examination,
                             "title": f'Thống kê tần suất đặt lịch khám theo các tháng trong năm {year_number}'})


def get_medicines_stats(request):
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        medicines = PrescriptionDetail.objects

        quarter_number = int(quarter)
        year_number = int(year)

        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            medicines = medicines.filter(created_date__quarter=quarter_number)

        # Get medicine data
        medicines = medicines.filter(created_date__year=year_number, active=True) \
            .values('medicine_unit__medicine__name') \
            .annotate(count=Count('medicine_unit')) \
            .values('medicine_unit__medicine__name', 'count')

        # Prepare medicine data for chart
        data_medicine_labels = []
        data_medicine_quantity = []
        for m in medicines:
            data_medicine_labels.append(m['medicine_unit__medicine__name'])
            data_medicine_quantity.append(m['count'])


    except Exception as ex:
        return HttpResponseServerError({"errMgs": "value Error"})
    else:
        return JsonResponse({"data_medicine_quantity": data_medicine_quantity,
                             "data_medicine_labels": data_medicine_labels,
                             "title": f'Thống kê tần suất sử dụng thuốc trong năm {year_number}'})


def getRandomColor():
    # Generate a random color in hexadecimal format
    r = lambda: random.randint(0, 255)
    return '#%02X%02X%02X' % (r(), r(), r())


from django.db.models import Q


def get_doctor_stats(request):
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        doctor_frequency = DoctorAvailability.objects

        quarter_number = int(quarter)
        year_number = int(year)
        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            doctor_frequency = doctor_frequency.filter(day__quarter=quarter_number)

        # Get doctor frequency data
        doctor_frequency = doctor_frequency.filter(day__year=year_number) \
            .annotate(month=TruncMonth('day')) \
            .values('doctor__id', 'doctor__first_name', 'doctor__last_name', 'doctor__email', 'month') \
            .annotate(count=Count('id')) \
            .values('doctor__id', 'doctor__first_name', 'doctor__last_name', 'doctor__email', 'month', 'count')

        data_doctor_labels = []
        data_doctor_quantity = []
        data_doctor_datasets = []
        for doctor in doctor_frequency:
            data_doctor_labels.append(doctor.get('doctor__first_name') + " " + doctor.get('doctor__last_name'))
            data_doctor_quantity.append(doctor.get('count'))

            doctor_name = doctor.get('doctor__first_name') + " " + doctor.get('doctor__last_name')
            count = doctor.get('count')
            month = doctor.get('month').month - 1

            # Check if the dataset for the current doctor already exists
            dataset = next((d for d in data_doctor_datasets if d['label'] == doctor_name), None)
            if dataset:
                dataset['data'][month] = count  # Update the count for the corresponding month
            else:
                data = [0] * 12
                data[month] = count
                dataset = {
                    'label': doctor_name,
                    'data': data,
                    # 'backgroundColor': random.choice(colors),
                    'borderColor': random.choice(colors),
                    'fill': False
                }
                data_doctor_datasets.append(dataset)

        if data_doctor_datasets:
            print(data_doctor_datasets)
    except Exception as ex:
        return HttpResponseServerError({"errMsg": "Value Error"})
    else:
        return JsonResponse({
            "data_doctor_labels": data_doctor_labels,
            "data_doctor_quantity": data_doctor_quantity,
            "data_doctor_datasets": data_doctor_datasets,
            "title": f'Thống kê tần suất khám của từng bác sĩ trong năm {year_number}'
        })