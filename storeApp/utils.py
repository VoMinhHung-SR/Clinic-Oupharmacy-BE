"""
Utility functions để hỗ trợ query cross-database và quản lý batch/notification
"""
from mainApp.models import User, MedicineUnit
from .models import Order, Brand, MedicineBatch, Notification


def get_order_with_details(order_number):
    """
    Lấy Order kèm thông tin User và MedicineUnits
    
    Returns:
        dict: {
            'order': Order object,
            'user': User object hoặc None,
            'items': [
                {
                    'item': OrderItem,
                    'medicine_unit': MedicineUnit
                }
            ]
        }
    """
    try:
        order = Order.objects.select_related('shipping_method', 'payment_method').prefetch_related('items').get(
            order_number=order_number
        )
    except Order.DoesNotExist:
        return None
    
    result = {
        'order': order,
        'user': None,
        'items': []
    }
    
    # Lấy User từ default database
    if order.user_id:
        try:
            result['user'] = User.objects.using('default').get(id=order.user_id)
        except User.DoesNotExist:
            pass
    
    # Lấy MedicineUnits từ default database
    medicine_unit_ids = [item.medicine_unit_id for item in order.items.all()]
    if medicine_unit_ids:
        medicine_units = {
            mu.id: mu for mu in MedicineUnit.objects.using('default').select_related('medicine', 'category').filter(
                id__in=medicine_unit_ids
            )
        }
        
        for item in order.items.all():
            medicine_unit = medicine_units.get(item.medicine_unit_id)
            result['items'].append({
                'item': item,
                'medicine_unit': medicine_unit
            })
    
    return result


def get_medicine_unit_with_brand(medicine_unit_id):
    """
    Lấy MedicineUnit kèm thông tin Brand nếu có
    
    Returns:
        dict: {
            'medicine_unit': MedicineUnit,
            'brand': Brand object hoặc None
        }
    """
    try:
        medicine_unit = MedicineUnit.objects.using('default').select_related('medicine', 'category').get(
            id=medicine_unit_id
        )
    except MedicineUnit.DoesNotExist:
        return None
    
    result = {
        'medicine_unit': medicine_unit,
        'brand': None
    }
    
    # Lấy Brand từ store database
    if medicine_unit.brand_id:
        try:
            result['brand'] = Brand.objects.get(id=medicine_unit.brand_id)
        except Brand.DoesNotExist:
            pass
    
    return result


def get_medicine_batches_with_details(medicine_unit_id):
    """
    Lấy tất cả batches của một MedicineUnit kèm thông tin chi tiết
    
    Returns:
        list: List of MedicineBatch objects với thông tin expiry status
    """
    batches = MedicineBatch.objects.filter(
        medicine_unit_id=medicine_unit_id,
        active=True
    ).order_by('expiry_date', 'import_date')
    
    return batches


def get_near_expiry_batches(days_threshold=30):
    """
    Lấy tất cả batches sắp hết hạn
    
    Args:
        days_threshold: Số ngày trước khi hết hạn để cảnh báo (default: 30)
    
    Returns:
        QuerySet: MedicineBatch objects sắp hết hạn
    """
    from django.utils import timezone
    from datetime import timedelta
    
    expiry_date_threshold = timezone.now().date() + timedelta(days=days_threshold)
    
    return MedicineBatch.objects.filter(
        active=True,
        remaining_quantity__gt=0,
        expiry_date__lte=expiry_date_threshold,
        expiry_date__gte=timezone.now().date()
    ).order_by('expiry_date')


def get_unread_notifications_count():
    """Lấy số lượng thông báo chưa đọc"""
    return Notification.objects.filter(is_read=False).count()


def get_unread_notifications(limit=10):
    """
    Lấy danh sách thông báo chưa đọc
    
    Args:
        limit: Số lượng thông báo tối đa (default: 10)
    
    Returns:
        QuerySet: Notification objects chưa đọc
    """
    return Notification.objects.filter(is_read=False).order_by('-created_date')[:limit]

