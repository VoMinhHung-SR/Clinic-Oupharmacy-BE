# Cart-first Checkout - Guideline

Tài liệu này chuẩn hóa flow checkout theo hướng **cart-first** cho Store API.

## 1) Mục tiêu

- Dùng `Cart` làm nguồn sự thật trước khi tạo `Order`.
- Tập trung pricing + voucher validation ở cart/service layer.
- Giảm race condition khi nhiều request mutate cart cùng lúc.

## 2) Luồng chuẩn (khuyến nghị)

1. `GET /api/store/carts/current/`
2. Mutate cart qua các endpoint `carts/`* (items, shipping, voucher, recalculate)
3. `POST /api/store/carts/checkout/`

Flow này là luồng chính cần ưu tiên cho FE và các tích hợp mới.

## 3) Endpoints cart-first

- `GET /api/store/carts/current/`
- `POST /api/store/carts/items/`
- `PATCH /api/store/carts/items/{item_id}/`
- `DELETE /api/store/carts/items/{item_id}/`
- `POST /api/store/carts/select-shipping/`
- `POST /api/store/carts/apply-voucher/`
- `POST /api/store/carts/remove-voucher/`
- `POST /api/store/carts/recalculate/`
- `POST /api/store/carts/checkout/`

## 4) Concurrency contract (`expected_version`)

Mọi endpoint mutate cart phải nhận `expected_version`.

Nguồn lấy version:

- từ `GET /api/store/carts/current/`
- hoặc response cart gần nhất sau mutate.

Nếu version stale, API trả `409 Conflict` với payload có:

- `details.expected_version`
- `details.current_version`

## 5) FE retry policy khi gặp `409`

1. Gọi lại `GET /api/store/carts/current/`
2. Cập nhật UI theo snapshot cart mới nhất
3. Retry action với `expected_version` mới

Lưu ý: Không retry mù nhiều lần với version cũ.

## 6) Tương thích endpoint cũ

`POST /api/store/orders/` vẫn hỗ trợ:

- `cart_id` branch (đi qua cart checkout service)
- raw-items branch legacy

Quy ước:

- Ưu tiên flow `carts/checkout` cho feature mới.
- Raw-items trong `orders.create` là đường legacy để backward compatibility.

## 7) Cache behavior hiện tại

- `carts/current` hỗ trợ read-through cache qua `CartCacheGateway`.
- Mutate/checkout có invalidate cache hooks trong cart service.
- Backend cache hiện tại là `Noop` mặc định; có thể cắm Redis sau mà không đổi flow nghiệp vụ.

## 8) Checklist verify nhanh

1. `GET /api/store/carts/current/` lấy được cart + `version`.
2. Mutate thành công khi gửi đúng `expected_version`.
3. Mutate bị `409` khi gửi version cũ.
4. `POST /api/store/carts/checkout/` tạo order thành công.
5. `POST /api/store/orders/` branch `cart_id` vẫn hoạt động cho compatibility.

