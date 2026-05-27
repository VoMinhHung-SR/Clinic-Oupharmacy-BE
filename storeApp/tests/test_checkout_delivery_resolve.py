"""Pure unit tests for checkout shipping address resolution."""
from django.test import SimpleTestCase

class CheckoutDeliveryResolveTests(SimpleTestCase):
    def test_legacy_nonempty_string_wins(self):
        from storeApp.services.checkout_delivery import resolve_checkout_shipping_address

        legacy = "  Only legacy text  "
        delivery = {
            "orderer": {"name": "X", "phone": "0382590839"},
            "recipient": {"name": "Y", "phone": "0382590839"},
            "address": {"detail": "123 Đường ABC"},
        }
        text, err = resolve_checkout_shipping_address(shipping_address=legacy, delivery=delivery)
        self.assertIsNone(err)
        self.assertEqual(text, "Only legacy text")

    def test_delivery_builds_multiline_address(self):
        from storeApp.services.checkout_delivery import resolve_checkout_shipping_address

        delivery = {
            "orderer": {"name": "Đặt Hàng", "phone": "0382590839", "email": "u@example.com"},
            "recipient": {"name": "Nhận Hàng", "phone": "0382590839"},
            "address": {
                "province": "Hà Nội",
                "district": "Ba Đình",
                "ward": "Phường 1",
                "detail": "12 Ngõ 3",
            },
        }
        text, err = resolve_checkout_shipping_address(shipping_address="", delivery=delivery)
        self.assertIsNone(err)
        self.assertIn("Người đặt:", text)
        self.assertIn("Email người đặt:", text)
        self.assertIn("Người nhận:", text)
        self.assertIn("Địa chỉ hành chính sau sáp nhập:", text)
        self.assertIn("Địa chỉ cụ thể:", text)

    def test_neither_string_nor_delivery_errors(self):
        from storeApp.services.checkout_delivery import resolve_checkout_shipping_address

        text, err = resolve_checkout_shipping_address(shipping_address="   ", delivery=None)
        self.assertIsNone(text)
        self.assertIsNotNone(err)

