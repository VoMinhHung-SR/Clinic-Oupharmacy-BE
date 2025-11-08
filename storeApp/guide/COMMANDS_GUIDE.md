# Store App - Commands Guide

Hướng dẫn sử dụng các management commands của storeApp.

## 📋 Danh sách Commands

### 1. Tạo dữ liệu demo

Tạo dữ liệu mẫu để test và development.

```bash
python manage.py create_demo_data
```

**Dữ liệu được tạo:**
- ✅ 9 Brands (Traphaco, Hậu Giang, Imexpharm, Domesco, Pharmedic, Opc, Sanofi, Abbott, Pfizer)
- ✅ 4 Shipping Methods (Giao nhanh, Giao tiêu chuẩn, Giao tiết kiệm, Giao trong giờ hành chính)
- ✅ 5 Payment Methods (COD, MoMo, VNPay, ZaloPay, Bank Transfer)
- ✅ 6 Medicine Batches (với các trạng thái khác nhau: sắp hết hạn, cảnh báo, bình thường, đã hết hạn)
- ✅ 3 Sample Notifications

**Lưu ý:**
- Command sử dụng `get_or_create`, nên chạy nhiều lần sẽ không bị duplicate
- Medicine batches được tạo với `medicine_unit_id` từ 1-5 (giả định đã có MedicineUnit trong database default)

---

### 2. Xóa dữ liệu demo

Xóa tất cả dữ liệu demo trong storeApp.

```bash
# Xóa với xác nhận
python manage.py clear_demo_data

# Xóa không cần xác nhận (cho automation/CI)
python manage.py clear_demo_data --confirm
```

**Dữ liệu bị xóa:**
- ❌ Tất cả Brands
- ❌ Tất cả Shipping Methods
- ❌ Tất cả Payment Methods
- ❌ Tất cả Orders và Order Items
- ❌ Tất cả Medicine Batches
- ❌ Tất cả Notifications

**⚠️ Cảnh báo:**
- Command này sẽ xóa TẤT CẢ dữ liệu trong các tables trên
- Nên chỉ dùng trong môi trường development/testing
- Dữ liệu trong database `default` (MedicineUnit, User, etc.) KHÔNG bị ảnh hưởng

---

### 3. Kiểm tra và tạo thông báo hết hạn

Tự động kiểm tra Medicine Batches và tạo notifications cho thuốc sắp hết hạn.

```bash
# Chạy với mặc định (cảnh báo 30 ngày, khẩn cấp 7 ngày)
python manage.py check_expiry_notifications

# Tùy chỉnh số ngày
python manage.py check_expiry_notifications --warning-days=30 --urgent-days=7
```

**Cách hoạt động:**
- Kiểm tra tất cả Medicine Batches có `remaining_quantity > 0`
- Tạo notification nếu:
  - `EXPIRY_WARNING`: Còn ≤ 30 ngày (mặc định)
  - `EXPIRY_URGENT`: Còn ≤ 7 ngày (mặc định)
  - `EXPIRED`: Đã hết hạn
- Không tạo duplicate notification trong cùng ngày

**Schedule tự động (Celery Beat):**
```python
CELERY_BEAT_SCHEDULE = {
    'check-expiry-notifications': {
        'task': 'storeApp.tasks.check_expiry_notifications',
        'schedule': crontab(hour=9, minute=0),  # Chạy mỗi ngày lúc 9h
    },
}
```

---

## 🚀 Workflow Development

### Setup ban đầu

```bash
# 1. Tạo dữ liệu demo
python manage.py create_demo_data

# 2. Kiểm tra thông báo hết hạn
python manage.py check_expiry_notifications
```

### Reset dữ liệu

```bash
# Xóa và tạo lại
python manage.py clear_demo_data --confirm
python manage.py create_demo_data
```

### Kiểm tra notifications

```bash
# Tạo notifications mới
python manage.py check_expiry_notifications

# Xem trong Django Admin
# http://localhost:8000/admin/storeApp/notification/
```

---

## 📁 Cấu trúc Models

### Models trong Store Database

- **Brand**: Thương hiệu sản phẩm
- **ShippingMethod**: Phương thức vận chuyển
- **PaymentMethod**: Phương thức thanh toán
- **Order**: Đơn hàng online
- **OrderItem**: Chi tiết đơn hàng
- **MedicineBatch**: Quản lý lô thuốc (ngày nhập, hạn sử dụng)
- **Notification**: Thông báo cảnh báo hết hạn

### Models trong Default Database (tham chiếu)

- **MedicineUnit**: Đơn vị thuốc (có field `brand_id` để liên kết với Brand)
- **User**: Người dùng (dùng `user_id` trong Order)

---

## 🔍 Utility Functions

Các helper functions có sẵn trong `storeApp/utils.py`:

```python
from storeApp.utils import (
    get_order_with_details,           # Lấy Order kèm User và MedicineUnits
    get_medicine_unit_with_brand,     # Lấy MedicineUnit kèm Brand
    get_medicine_batches_with_details, # Lấy batches của một MedicineUnit
    get_near_expiry_batches,          # Lấy batches sắp hết hạn
    get_unread_notifications_count,   # Đếm notifications chưa đọc
    get_unread_notifications,         # Lấy danh sách notifications chưa đọc
)
```

---

## ⚠️ Lưu ý quan trọng

1. **Cross-database queries**: Models trong `storeApp` và `mainApp` ở 2 database khác nhau
   - Phải dùng `.using('default')` hoặc `.using('store')` khi query cross-database
   - Không thể dùng ForeignKey trực tiếp giữa 2 databases

2. **Medicine Batch**: Cần tạo MedicineBatch khi nhập thuốc mới vào kho
   ```python
   MedicineBatch.objects.create(
       batch_number='BATCH001',
       medicine_unit_id=1,  # ID từ MedicineUnit
       import_date=date.today(),
       expiry_date=date.today() + timedelta(days=365),
       quantity=100,
       remaining_quantity=100,
   )
   ```

3. **Order Number**: Tự động generate khi tạo Order (format: ORDYYYYMMDDXXXX)

---

## 📞 Hỗ trợ

Nếu gặp vấn đề:
1. Kiểm tra database connection trong `settings.py`
2. Đảm bảo đã chạy migrations: `python manage.py migrate --database=store`
3. Kiểm tra `STORE_DATABASE_URL_PG` trong `.env`

