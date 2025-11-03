# Hướng dẫn Triển khai Store App

## Tổng quan

Đã tạo app `storeApp` với kiến trúc **Multiple Databases** để tách biệt dữ liệu e-commerce nhưng vẫn có thể truy vấn các models chung từ database chính.

## Những gì đã được tạo

### 1. Models Core (MVP)
- ✅ **Brand**: Thương hiệu sản phẩm
- ✅ **ShippingMethod**: Phương thức vận chuyển
- ✅ **PaymentMethod**: Phương thức thanh toán
- ✅ **Order**: Đơn hàng online với auto-generate order_number
- ✅ **OrderItem**: Chi tiết đơn hàng

### 2. Database Router
- ✅ **StoreRouter**: Tự động route models của `storeApp` sang database `store`
- ✅ Models khác tự động dùng database `default`

### 3. Cấu hình
- ✅ Thêm `storeApp` vào `INSTALLED_APPS`
- ✅ Cấu hình multiple databases trong `settings.py`
- ✅ Thêm `brand_id` field vào `MedicineUnit` để tham chiếu Brand

### 4. Admin Interface
- ✅ Django Admin đã được cấu hình cho tất cả models

### 5. Utilities
- ✅ Helper functions để query cross-database dễ dàng

## Bước tiếp theo - Migrations

### 1. Tạo migrations cho storeApp

```bash
python manage.py makemigrations storeApp
```

### 2. Chạy migrations cho store database

```bash
python manage.py migrate --database=store
```

### 3. Nếu cần, chạy migrations cho MedicineUnit.brand_id

```bash
python manage.py makemigrations mainApp
python manage.py migrate --database=default
```

## Cấu hình Database

### Option 1: Dùng chung database (Development)

Không cần cấu hình gì thêm. Django sẽ tự động tạo database với suffix `_store` nếu không có `STORE_DATABASE_URL_PG`.

### Option 2: Dùng database riêng (Production)

Thêm vào file `.env`:

```env
STORE_DATABASE_URL_PG=postgresql://user:password@localhost:5432/store_db
```

## Ví dụ sử dụng

### Tạo Order

```python
from storeApp.models import Order, OrderItem, ShippingMethod, PaymentMethod
from mainApp.models import User, MedicineUnit

# Lấy user và shipping/payment methods
user = User.objects.using('default').get(email='customer@example.com')
shipping = ShippingMethod.objects.get(id=1)
payment = PaymentMethod.objects.get(code='COD')

# Tạo order (order_number sẽ tự động generate)
order = Order.objects.create(
    user_id=user.id,  # Lưu ID, không phải object
    shipping_address='123 Đường ABC, Quận 1, TP.HCM',
    shipping_method=shipping,
    payment_method=payment,
    subtotal=500000,
    shipping_fee=25000,
    total=525000,
    status=Order.PENDING
)

# Tạo order items
medicine_unit = MedicineUnit.objects.using('default').get(id=1)
OrderItem.objects.create(
    order=order,
    medicine_unit_id=medicine_unit.id,  # Lưu ID
    quantity=2,
    price=250000
)
```

### Query Order với thông tin đầy đủ

```python
from storeApp.utils import get_order_with_details

# Lấy order kèm User và MedicineUnits
order_data = get_order_with_details('ORD202501010001')

if order_data:
    order = order_data['order']
    user = order_data['user']  # User object hoặc None
    items = order_data['items']  # List of {item, medicine_unit}
    
    for item_data in items:
        item = item_data['item']  # OrderItem
        medicine_unit = item_data['medicine_unit']  # MedicineUnit object
        print(f"{medicine_unit.medicine.name} x{item.quantity} = {item.subtotal}")
```

## Lưu ý quan trọng

### 1. Cross-database Foreign Keys
Không thể dùng `ForeignKey` trực tiếp giữa 2 databases. Phải dùng `BigIntegerField` và query thủ công:

```python
# ❌ SAI - Không thể làm vậy
order.user  # Không hoạt động

# ✅ ĐÚNG
user = User.objects.using('default').get(id=order.user_id)
```

### 2. Transactions
Không thể dùng transaction chung cho 2 databases:

```python
from django.db import transaction

# ❌ SAI - Chỉ áp dụng cho 1 database
with transaction.atomic():
    order.save()
    user.save()  # user ở database khác

# ✅ ĐÚNG - Phải handle riêng
try:
    with transaction.atomic(using='store'):
        order.save()
    with transaction.atomic(using='default'):
        user.save()
except Exception:
    # Handle rollback
    pass
```

### 3. Queries
Luôn chỉ định database khi query cross-database:

```python
# Models trong storeApp tự động dùng database 'store'
orders = Order.objects.all()  # ✅ Đúng

# Models trong mainApp tự động dùng database 'default'
users = User.objects.all()  # ✅ Đúng

# Khi query cross-database, phải chỉ định
user = User.objects.using('default').get(id=order.user_id)  # ✅ Đúng
```

## Cấu trúc Files

```
storeApp/
├── __init__.py
├── apps.py
├── models.py          # Brand, ShippingMethod, PaymentMethod, Order, OrderItem
├── admin.py           # Django admin configuration
├── db_router.py       # Database routing logic
├── utils.py           # Helper functions cho cross-database queries
├── README.md          # Documentation
└── IMPLEMENTATION_GUIDE.md  # File này
```

## Testing

Sau khi chạy migrations, test trong Django shell:

```bash
python manage.py shell
```

```python
# Test tạo Brand
from storeApp.models import Brand
brand = Brand.objects.create(name="Traphaco", active=True)
print(brand)

# Test tạo ShippingMethod
from storeApp.models import ShippingMethod
shipping = ShippingMethod.objects.create(
    name="Giao nhanh",
    price=25000,
    estimated_days=1,
    active=True
)
print(shipping)

# Test tạo Order
from storeApp.models import Order, PaymentMethod
payment = PaymentMethod.objects.create(name="COD", code="COD", active=True)
order = Order.objects.create(
    user_id=1,
    shipping_address="123 ABC",
    shipping_method=shipping,
    payment_method=payment,
    subtotal=100000,
    shipping_fee=25000,
    total=125000
)
print(order.order_number)  # Sẽ tự động generate
```

## Support

Nếu gặp vấn đề, kiểm tra:
1. Database connections trong `settings.py`
2. Router configuration
3. Migrations đã chạy đầy đủ chưa
4. Environment variables đã set đúng chưa

