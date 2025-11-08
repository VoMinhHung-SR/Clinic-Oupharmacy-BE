from django.http import JsonResponse, HttpResponseForbidden, HttpResponseServerError
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from datetime import date
from .models import Order


def get_store_revenue_stats(request):
    """Thống kê doanh thu đơn hàng online theo tháng"""
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        orders = Order.objects.filter(status=Order.DELIVERED)  # Chỉ tính đơn đã giao
        quarter_number = int(quarter)
        year_number = int(year)
        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            orders = orders.filter(created_date__quarter=quarter_number)

        orders = orders.filter(created_date__year=year_number) \
            .annotate(month=TruncMonth('created_date')) \
            .values('month').annotate(total=Sum("total"), count=Count("id")).values('month', 'total', 'count')
        
        data_revenue = [0] * 12
        for rs in orders:
            month = rs['month'].month - 1
            data_revenue[month] = rs['total']

    except Exception as ex:
        return HttpResponseServerError({"errMsg": "Lỗi xử lý dữ liệu"})
    else:
        return JsonResponse({
            "data_revenue": data_revenue,
            "title": f'Thống kê doanh thu đơn hàng online theo các tháng trong năm {year_number}'
        })


def get_store_orders_stats(request):
    """Thống kê số lượng đơn hàng theo tháng"""
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        orders = Order.objects
        quarter_number = int(quarter)
        year_number = int(year)

        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            orders = orders.filter(created_date__quarter=quarter_number)

        orders = orders.filter(created_date__year=year_number) \
            .annotate(month=TruncMonth('created_date')) \
            .values('month').annotate(count=Count('pk')).values('month', 'count')

        data_orders = [0] * 12
        for rs in orders:
            month = rs['month'].month - 1
            data_orders[month] = rs['count']

    except Exception as ex:
        return HttpResponseServerError({"errMsg": "Lỗi xử lý dữ liệu"})
    else:
        return JsonResponse({
            "data_orders": data_orders,
            "title": f'Thống kê số lượng đơn hàng theo các tháng trong năm {year_number}'
        })


def get_store_payment_methods_stats(request):
    """Thống kê đơn hàng theo phương thức thanh toán"""
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        orders = Order.objects
        quarter_number = int(quarter)
        year_number = int(year)

        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            orders = orders.filter(created_date__quarter=quarter_number)

        payment_stats = orders.filter(created_date__year=year_number) \
            .values('payment_method__name', 'payment_method__code') \
            .annotate(count=Count('id'), total=Sum('total')) \
            .values('payment_method__name', 'payment_method__code', 'count', 'total')

        data_labels = []
        data_count = []
        data_total = []
        for stat in payment_stats:
            data_labels.append(stat['payment_method__name'] or stat['payment_method__code'])
            data_count.append(stat['count'])
            data_total.append(float(stat['total'] or 0))

    except Exception as ex:
        return HttpResponseServerError({"errMsg": "Lỗi xử lý dữ liệu"})
    else:
        return JsonResponse({
            "data_labels": data_labels,
            "data_count": data_count,
            "data_total": data_total,
            "title": f'Thống kê đơn hàng theo phương thức thanh toán trong năm {year_number}'
        })


def get_store_shipping_methods_stats(request):
    """Thống kê đơn hàng theo phương thức vận chuyển"""
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        orders = Order.objects
        quarter_number = int(quarter)
        year_number = int(year)

        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            orders = orders.filter(created_date__quarter=quarter_number)

        shipping_stats = orders.filter(created_date__year=year_number) \
            .values('shipping_method__name') \
            .annotate(count=Count('id'), total=Sum('total')) \
            .values('shipping_method__name', 'count', 'total')

        data_labels = []
        data_count = []
        data_total = []
        for stat in shipping_stats:
            data_labels.append(stat['shipping_method__name'])
            data_count.append(stat['count'])
            data_total.append(float(stat['total'] or 0))

    except Exception as ex:
        return HttpResponseServerError({"errMsg": "Lỗi xử lý dữ liệu"})
    else:
        return JsonResponse({
            "data_labels": data_labels,
            "data_count": data_count,
            "data_total": data_total,
            "title": f'Thống kê đơn hàng theo phương thức vận chuyển trong năm {year_number}'
        })


def get_store_order_status_stats(request):
    """Thống kê đơn hàng theo trạng thái"""
    if request.user.is_anonymous or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        quarter = request.GET.get('quarter', '0')
        year = request.GET.get('year', '0')

        orders = Order.objects
        quarter_number = int(quarter)
        year_number = int(year)

        if year_number == 0:
            year_number = date.today().year

        if quarter_number > 0:
            orders = orders.filter(created_date__quarter=quarter_number)

        status_stats = orders.filter(created_date__year=year_number) \
            .values('status') \
            .annotate(count=Count('id'), total=Sum('total')) \
            .values('status', 'count', 'total')

        data_labels = []
        data_count = []
        data_total = []
        status_display = dict(Order.STATUS_CHOICES)
        
        for stat in status_stats:
            status_key = stat['status']
            data_labels.append(status_display.get(status_key, status_key))
            data_count.append(stat['count'])
            data_total.append(float(stat['total'] or 0))

    except Exception as ex:
        return HttpResponseServerError({"errMsg": "Lỗi xử lý dữ liệu"})
    else:
        return JsonResponse({
            "data_labels": data_labels,
            "data_count": data_count,
            "data_total": data_total,
            "title": f'Thống kê đơn hàng theo trạng thái trong năm {year_number}'
        })

