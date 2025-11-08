# Store App - E-commerce Module

Module quản lý đơn hàng online cho OUPharmacy Store, sử dụng database riêng nhưng vẫn truy vấn được các models chung (User, Medicine) từ database chính.

## Kiến trúc Database

- **Database `default`**: Chứa các models của Clinic app (User, Medicine, MedicineUnit, Category, Patient, etc.)
- **Database `store`**: Chứa các models của Store app (Brand, Order, OrderItem, ShippingMethod, PaymentMethod)

## Models

### Brand
Thương hiệu sản phẩm
- `name`: Tên thương hiệu (unique)
- `active`: Trạng thái hoạt động

### ShippingMethod
Phương thức vận chuyển
- `name`: Tên phương thức
- `price`: Phí vận chuyển
- `estimated_days`: Số ngày ước tính
- `active`: Trạng thái

### PaymentMethod
Phương thức thanh toán
- `name`: Tên phương thức
- `code`: Mã định danh (COD, MOMO, VNPAY...)
- `active`: Trạng thái

### Order
Đơn hàng online
- `order_number`: Mã đơn hàng (unique, auto-generate)
- `user_id`: ID của User trong database default (BigInteger, không có FK constraint)
- `shipping_address`: Địa chỉ giao hàng
- `shipping_method`: FK → ShippingMethod
- `payment_method`: FK → PaymentMethod
- `subtotal`: Tổng tiền sản phẩm
- `shipping_fee`: Phí vận chuyển
- `total`: Tổng thanh toán
- `status`: Trạng thái (PENDING, CONFIRMED, SHIPPING, DELIVERED, CANCELLED)
- `notes`: Ghi chú

### OrderItem
Chi tiết đơn hàng
- `order`: FK → Order
- `medicine_unit_id`: ID của MedicineUnit trong database default (BigInteger, không có FK constraint)
- `quantity`: Số lượng
- `price`: Giá tại thời điểm đặt hàng (snapshot)

## Cách sử dụng

### Truy vấn cross-database

```python
# Lấy Order từ store database
order = Order.objects.get(order_number='ORD001')

# Lấy User từ default database
user = User.objects.using('default').get(id=order.user_id)

# Lấy MedicineUnit từ default database
for item in order.items.all():
    medicine_unit = MedicineUnit.objects.using('default').get(id=item.medicine_unit_id)
    print(f"{medicine_unit.medicine.name} x{item.quantity}")
```

### Tạo Order mới

```python
from storeApp.models import Order, OrderItem, ShippingMethod, PaymentMethod

# Lấy shipping và payment method
shipping = ShippingMethod.objects.get(id=1)
payment = PaymentMethod.objects.get(code='COD')

# Tạo order
order = Order.objects.create(
    order_number='ORD001',  # Tự generate trong thực tế
    user_id=user.id,  # ID từ User object
    shipping_address='123 Đường ABC',
    shipping_method=shipping,
    payment_method=payment,
    subtotal=500000,
    shipping_fee=25000,
    total=525000,
    status=Order.PENDING
)

# Tạo order items
OrderItem.objects.create(
    order=order,
    medicine_unit_id=medicine_unit.id,  # ID từ MedicineUnit object
    quantity=2,
    price=250000
)
```

## Migrations

### Tạo migrations
```bash
python manage.py makemigrations storeApp
```

### Chạy migrations cho store database
```bash
python manage.py migrate --database=store
```

### Chạy migrations cho default database (nếu có thay đổi ở MedicineUnit)
```bash
python manage.py migrate --database=default
```

## Cấu hình Database

Thêm vào file `.env`:

```env
# Database chính cho Clinic app
DATABASE_URL_PG=postgresql://user:password@localhost:5432/clinic_db

# Database riêng cho Store app (optional)
# Nếu không có, sẽ tự động tạo database với suffix _store
STORE_DATABASE_URL_PG=postgresql://user:password@localhost:5432/store_db
```

## Lưu ý quan trọng

1. **Cross-database Foreign Keys**: Không thể dùng ForeignKey trực tiếp giữa 2 databases. Phải dùng `BigIntegerField` để lưu ID và query thủ công.

2. **Transactions**: Không thể dùng transaction chung cho 2 databases. Phải handle rollback riêng biệt.

3. **Queries**: Luôn chỉ định database khi query cross-database bằng `.using('database_name')`.

4. **MedicineUnit.brand_id**: Field này lưu ID của Brand trong store database, không có FK constraint.

