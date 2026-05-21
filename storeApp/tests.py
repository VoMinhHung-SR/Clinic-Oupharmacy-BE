import uuid

from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model

from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from unittest.mock import Mock, patch

from storeApp.models import (
    Brand,
    Category,
    Product,
    ProductVariant,
    ProductVariantUnit,
    SearchKeyword,
    ShippingMethod,
    PaymentMethod,
    MedicineBatch,
    Voucher,
    VoucherRedemption,
    Order,
    Cart,
)


class SearchKeywordApiTests(APITestCase):
    databases = {"default", "store"}

    def test_record_search_deduplicates_and_increments_hit_count(self):
        first = self.client.post(
            "/api/store/search-terms/",
            {"keyword": "Vitamin"},
            format="json",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            "/api/store/search-terms/",
            {"keyword": "  vItAmIn  "},
            format="json",
        )
        self.assertEqual(second.status_code, 201)

        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(second.data["hit_count"], first.data["hit_count"] + 1)
        self.assertEqual(SearchKeyword.objects.count(), 1)


class SearchSuggestApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.create(name="Thuốc cảm cúm", slug="thuoc-cam-cum")

        for idx in range(6):
            product = Product.objects.create(
                name=f"Sản phẩm cảm cúm {idx}",
                web_name=f"Thuốc trị cảm cúm {idx}",
                slug=f"thuoc-tri-cam-cum-{idx}",
                category=self.category,
            )
            variant = ProductVariant.objects.create(
                product=product,
                packing="Hộp",
                is_published=True,
                in_stock=100 - idx,
                product_ranking=90 - idx,
            )
            ProductVariantUnit.objects.create(
                variant=variant,
                unit_name="Hộp",
                quantity_in_base=1,
                price_value=10000 + idx,
                is_default=True,
                is_published=True,
            )

        kw_1 = SearchKeyword.objects.create(keyword="cảm cúm")
        kw_2 = SearchKeyword.objects.create(keyword="cảm cúm trẻ em")
        SearchKeyword.objects.filter(pk=kw_1.pk).update(
            hit_count=10,
            last_searched_at=timezone.now(),
        )
        SearchKeyword.objects.filter(pk=kw_2.pk).update(
            hit_count=5,
            last_searched_at=timezone.now(),
        )

    def test_search_suggest_returns_expected_groups_and_top5_limit(self):
        response = self.client.get("/api/store/search/suggest/?q=cảm cúm")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["query"], "cảm cúm")

        suggestions = response.data["suggestions"]
        self.assertIn("history_search", suggestions)
        self.assertIn("hot_search", suggestions)
        self.assertIn("categories", suggestions)
        self.assertIn("top_products", suggestions)

        self.assertGreaterEqual(len(suggestions["history_search"]), 1)
        self.assertGreaterEqual(len(suggestions["hot_search"]), 1)
        self.assertGreaterEqual(len(suggestions["categories"]), 1)
        self.assertGreaterEqual(len(suggestions["top_products"]), 1)
        self.assertLessEqual(len(suggestions["top_products"]), 5)


class SearchApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.brand = Brand.objects.create(name="DHG", country="VN")
        self.category = Category.objects.create(name="Thuốc cảm", slug="thuoc-cam")
        self.other_category = Category.objects.create(name="Vitamin", slug="vitamin")

        self._create_variant(
            name="Thuốc cảm cúm A",
            web_name="Thuốc cảm cúm A Plus",
            slug="thuoc-cam-cum-a",
            category=self.category,
            price_value=90000,
            in_stock=5,
            ranking=90,
        )
        self._create_variant(
            name="Thuốc cảm cúm B",
            web_name="Viên cảm cúm B",
            slug="thuoc-cam-cum-b",
            category=self.category,
            price_value=220000,
            in_stock=0,
            ranking=70,
        )
        self._create_variant(
            name="Vitamin C",
            web_name="Vitamin C 1000",
            slug="vitamin-c-1000",
            category=self.other_category,
            price_value=550000,
            in_stock=8,
            ranking=80,
        )
        self._create_extra_variant_for_existing_product(
            slug="thuoc-cam-cum-a",
            packing="Hộp 6 vỉ x 10 viên",
            price_value=120000,
            in_stock=3,
            ranking=60,
        )

    def _create_variant(self, name, web_name, slug, category, price_value, in_stock, ranking):
        product = Product.objects.create(
            name=name,
            web_name=web_name,
            slug=slug,
            category=category,
            brand=self.brand,
        )
        variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp",
            is_published=True,
            in_stock=in_stock,
            product_ranking=ranking,
        )
        ProductVariantUnit.objects.create(
            variant=variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=price_value,
            is_default=True,
            is_published=True,
        )
        return variant

    def _create_extra_variant_for_existing_product(self, slug, packing, price_value, in_stock, ranking):
        product = Product.objects.get(slug=slug)
        variant = ProductVariant.objects.create(
            product=product,
            packing=packing,
            is_published=True,
            in_stock=in_stock,
            product_ranking=ranking,
        )
        ProductVariantUnit.objects.create(
            variant=variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=price_value,
            is_default=True,
            is_published=True,
        )
        return variant

    def test_search_returns_items_facets_and_meta(self):
        response = self.client.get("/api/store/search/?q=cảm cúm&page=1&page_size=2")
        self.assertEqual(response.status_code, 200)

        self.assertIn("items", response.data)
        self.assertIn("facets", response.data)
        self.assertIn("meta", response.data)
        self.assertEqual(response.data["meta"]["page"], 1)
        self.assertEqual(response.data["meta"]["page_size"], 2)
        self.assertEqual(response.data["meta"]["total"], 3)
        self.assertEqual(len(response.data["items"]), 2)
        first_item = response.data["items"][0]
        self.assertIn("unit_options", first_item)
        self.assertIn("default_unit_id", first_item)
        self.assertIn("default_unit_name", first_item)

    def test_search_applies_filters_and_reports_applied_filters(self):
        response = self.client.get(
            f"/api/store/search/?q=cảm cúm&category={self.category.id}&price_range=under_100k&in_stock=true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["meta"]["total"], 1)
        self.assertEqual(len(response.data["items"]), 1)

        applied = response.data["meta"]["applied_filters"]
        self.assertEqual(applied["category"], str(self.category.id))
        self.assertEqual(applied["price_range"], "under_100k")
        self.assertTrue(applied["in_stock"])

    def test_search_facets_include_expected_price_and_stock_counts(self):
        response = self.client.get("/api/store/search/?q=")
        self.assertEqual(response.status_code, 200)

        facets = response.data["facets"]
        price_counts = {item["key"]: item["count"] for item in facets["price_ranges"]}
        stock_counts = {item["key"]: item["count"] for item in facets["in_stock"]}

        self.assertEqual(price_counts["under_100k"], 1)
        self.assertEqual(price_counts["100k_300k"], 2)
        self.assertEqual(price_counts["300k_500k"], 0)
        self.assertEqual(price_counts["over_500k"], 1)
        self.assertEqual(stock_counts[True], 3)
        self.assertEqual(stock_counts[False], 1)


class OrderVoucherCreateTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="voucher-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.shipping_method = ShippingMethod.objects.create(
            name="Standard",
            price=30000,
            estimated_days=2,
            active=True,
        )
        self.payment_method = PaymentMethod.objects.create(
            name="COD",
            code="COD",
            active=True,
        )

        self.category = Category.objects.create(name="Thuốc ho", slug="thuoc-ho")
        self.product = Product.objects.create(
            name="Thuốc ho A",
            mid="MID-HOA",
            slug="thuoc-ho-a",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp",
            in_stock=200,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=1,
            unit_name="Hộp",
            unit_order=0,
            price_value=100000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-VOUCHER-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=7),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=200,
            remaining_quantity=200,
        )

    def _create_voucher(self, code, scope, voucher_type="PERCENT", value="10", **kwargs):
        defaults = {
            "code": code,
            "scope": scope,
            "type": voucher_type,
            "value": Decimal(str(value)),
            "is_active": True,
            "start_at": timezone.now() - timedelta(days=1),
            "end_at": timezone.now() + timedelta(days=1),
            "usage_limit": 10,
        }
        defaults.update(kwargs)
        return Voucher.objects.create(**defaults)

    def _payload(self, **extra):
        payload = {
            "shipping_address": "123 Test Street",
            "notes": "ghi chu",
            "shipping_method_id": self.shipping_method.id,
            "payment_method_id": self.payment_method.id,
            "items": [
                {
                    "product_variant_id": self.variant.id,
                    "product_variant_unit_id": self.unit.id,
                    "quantity": 1,
                    "price": "100000",
                }
            ],
            "subtotal": "1",
            "shipping_fee": "1",
            "total": "1",
        }
        payload.update(extra)
        return payload

    def test_create_order_applies_one_order_voucher_and_one_shipping_voucher(self):
        order_voucher = self._create_voucher(
            code="ORDER10",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="PERCENT",
            value="10",
            per_user_limit=2,
        )
        shipping_voucher = self._create_voucher(
            code="SHIP5",
            scope=Voucher.SHIPPING_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
        )

        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code, shipping_voucher_code=shipping_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["discount_amount"], "10000.00")
        self.assertEqual(response.data["shipping_discount_amount"], "5000.00")
        self.assertEqual(response.data["shipping_fee"], "25000.00")
        self.assertEqual(response.data["total"], "115000.00")
        self.assertEqual(response.data["order_voucher_code"], "ORDER10")
        self.assertEqual(response.data["shipping_voucher_code"], "SHIP5")

        order = Order.objects.get(id=response.data["id"])
        self.assertEqual(order.order_voucher_id, order_voucher.id)
        self.assertEqual(order.shipping_voucher_id, shipping_voucher.id)
        self.assertEqual(VoucherRedemption.objects.filter(order=order).count(), 2)

    def test_create_order_rejects_wrong_scope_codes(self):
        shipping_voucher = self._create_voucher(
            code="SHIPONLY",
            scope=Voucher.SHIPPING_DISCOUNT,
            voucher_type="FIXED",
            value="10000",
        )

        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=shipping_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("order_voucher_code must be ORDER_DISCOUNT voucher", response.data["error"])

    def test_create_order_enforces_per_user_limit(self):
        order_voucher = self._create_voucher(
            code="ONEPERUSER",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="10000",
            per_user_limit=1,
        )

        first = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(
            second.data["details"]["order_voucher_code"][0],
            "Per-user limit exceeded",
        )

    def test_create_order_total_is_calculated_server_side(self):
        response = self.client.post("/api/store/orders/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["subtotal"], "100000.00")
        self.assertEqual(response.data["shipping_fee"], "30000.00")
        self.assertEqual(response.data["total"], "130000.00")

    def test_create_order_rejects_voucher_not_started(self):
        order_voucher = self._create_voucher(
            code="NOTSTART",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=2),
        )
        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["details"]["order_voucher_code"][0], "Voucher is not started")

    def test_create_order_rejects_voucher_expired(self):
        order_voucher = self._create_voucher(
            code="EXPIRED",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
            start_at=timezone.now() - timedelta(days=4),
            end_at=timezone.now() - timedelta(days=1),
        )
        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["details"]["order_voucher_code"][0], "Voucher is expired")

    def test_create_order_rejects_usage_limit_reached(self):
        order_voucher = self._create_voucher(
            code="LIMITREACHED",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
            usage_limit=1,
            used_count=1,
        )
        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["details"]["order_voucher_code"][0],
            "Voucher usage limit exceeded",
        )

    def test_create_order_rejects_min_order_not_met(self):
        order_voucher = self._create_voucher(
            code="MIN200K",
            scope=Voucher.ORDER_DISCOUNT,
            voucher_type="FIXED",
            value="5000",
            min_order_value=Decimal("200000"),
        )
        response = self.client.post(
            "/api/store/orders/",
            self._payload(order_voucher_code=order_voucher.code),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["details"]["order_voucher_code"][0],
            "Minimum order value not met",
        )


class CartVersioningFlowTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="cart-version-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.shipping_method = ShippingMethod.objects.create(
            name="Standard",
            price=30000,
            estimated_days=2,
            active=True,
        )
        self.payment_method = PaymentMethod.objects.create(
            name="COD",
            code="COD",
            active=True,
        )
        self.category = Category.objects.create(name="Thuốc tim", slug="thuoc-tim")
        self.product = Product.objects.create(
            name="Thuốc tim A",
            mid="MID-CART-001",
            slug="thuoc-tim-a",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp",
            in_stock=100,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=1,
            unit_name="Hộp",
            unit_order=0,
            price_value=100000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-CART-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=5),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=100,
            remaining_quantity=100,
        )

    def _current_cart(self):
        response = self.client.get("/api/store/carts/current/")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_add_item_requires_expected_version(self):
        response = self.client.post(
            "/api/store/carts/items/",
            {
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "expected_version is required")

    def test_mutate_cart_returns_409_when_expected_version_is_stale(self):
        cart_data = self._current_cart()
        old_version = cart_data["version"]

        add_response = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": old_version,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add_response.status_code, 200)
        new_version = add_response.data["version"]
        self.assertTrue(new_version > old_version)

        stale_response = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": old_version,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(stale_response.status_code, 409)
        self.assertEqual(stale_response.data["details"]["expected_version"], old_version)
        self.assertEqual(stale_response.data["details"]["current_version"], new_version)

    def test_order_create_with_cart_id_returns_409_on_stale_expected_version(self):
        cart_data = self._current_cart()
        cart_id = cart_data["id"]
        old_version = cart_data["version"]

        add_response = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": old_version,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add_response.status_code, 200)
        latest_version = add_response.data["version"]

        shipping_response = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": latest_version,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(shipping_response.status_code, 200)

        response = self.client.post(
            "/api/store/orders/",
            {
                "cart_id": cart_id,
                "expected_version": old_version,
                "payment_method_id": self.payment_method.id,
                "shipping_address": "123 stale version street",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["details"]["expected_version"], old_version)
        self.assertTrue(response.data["details"]["current_version"] > old_version)


class CartCurrentCacheReadThroughTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="cart-cache-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

    @patch("storeApp.viewsets.cart.recalculate_cart")
    @patch("storeApp.viewsets.cart.get_cart_cache_gateway")
    def test_current_returns_cached_summary_when_cache_hit(self, mock_get_gateway, mock_recalculate):
        cached_summary = {"id": 777, "source": "cache", "total": "123.00"}
        gateway = Mock()
        gateway.get_cart_summary.return_value = cached_summary
        mock_get_gateway.return_value = gateway

        response = self.client.get("/api/store/carts/current/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, cached_summary)
        mock_recalculate.assert_not_called()
        gateway.set_cart_summary.assert_not_called()

    @patch("storeApp.viewsets.cart.get_cart_cache_gateway")
    def test_current_sets_cache_when_cache_miss(self, mock_get_gateway):
        gateway = Mock()
        gateway.get_cart_summary.return_value = None
        mock_get_gateway.return_value = gateway

        response = self.client.get("/api/store/carts/current/")
        self.assertEqual(response.status_code, 200)
        gateway.get_cart_summary.assert_called_once()
        gateway.set_cart_summary.assert_called_once()


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


class CartCheckoutDeliveryApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="checkout-delivery-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.shipping_method = ShippingMethod.objects.create(
            name="Standard",
            price=30000,
            estimated_days=2,
            active=True,
        )
        self.payment_method = PaymentMethod.objects.create(
            name="COD",
            code="COD",
            active=True,
        )
        self.category = Category.objects.create(name="Thuốc ho", slug="thuoc-ho")
        self.product = Product.objects.create(
            name="Thuốc ho A",
            mid="MID-CHK-DLV-001",
            slug="thuoc-ho-a",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp",
            in_stock=100,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=1,
            unit_name="Hộp",
            unit_order=0,
            price_value=50000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-CHK-DLV-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=5),
            expiry_date=timezone.now().date() + timedelta(days=365),
            quantity=100,
            remaining_quantity=100,
        )

    def _delivery_body(self):
        return {
            "orderer": {"name": "Đặt Hàng", "phone": "0382590839", "email": "orderer@example.com"},
            "recipient": {"name": "Nhận Hàng", "phone": "0382590839"},
            "address": {"province": "HN", "district": "Ba Đình", "ward": "P1", "detail": "12 Phố Huế"},
        }

    def test_carts_checkout_accepts_delivery_object(self):
        cart_data = self.client.get("/api/store/carts/current/").data
        v0 = cart_data["version"]

        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        v1 = add.data["version"]

        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": v1,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        v2 = ship.data["version"]

        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": v2,
                "payment_method_id": self.payment_method.id,
                "delivery": self._delivery_body(),
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        self.assertIn("Người đặt:", checkout.data["shipping_address"])
        self.assertIn("Người nhận:", checkout.data["shipping_address"])
        order = Order.objects.filter(user_id=self.user.id).order_by("-id").first()
        self.assertIsNotNone(order)
        self.assertIn("Email người đặt:", order.shipping_address)

    def test_carts_checkout_delivery_validation_error(self):
        cart_data = self.client.get("/api/store/carts/current/").data
        v0 = cart_data["version"]

        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        v1 = add.data["version"]

        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": v1,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        v2 = ship.data["version"]

        bad_delivery = {
            "orderer": {"name": "A", "phone": "invalid"},
            "recipient": {"name": "B", "phone": "0382590839"},
            "address": {"detail": "12 Phố Huế"},
        }
        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": v2,
                "payment_method_id": self.payment_method.id,
                "delivery": bad_delivery,
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 400)
        self.assertEqual(checkout.data.get("error"), "Validation failed")

    def test_carts_checkout_insufficient_stock_returns_400_not_500(self):
        cart_data = self.client.get("/api/store/carts/current/").data
        v0 = cart_data["version"]

        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 2,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        v1 = add.data["version"]

        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": v1,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        v2 = ship.data["version"]

        MedicineBatch.objects.filter(product_variant_id=self.variant.id).update(remaining_quantity=1)

        orders_before = Order.objects.filter(user_id=self.user.id).count()
        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": v2,
                "payment_method_id": self.payment_method.id,
                "delivery": self._delivery_body(),
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 400, checkout.data)
        self.assertIn("Insufficient stock", checkout.data.get("error", ""))
        self.assertEqual(Order.objects.filter(user_id=self.user.id).count(), orders_before)


class GuestCartCheckoutTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.guest_session_id = str(uuid.uuid4())
        self.client.credentials(HTTP_X_GUEST_SESSION=self.guest_session_id)

        self.shipping_method = ShippingMethod.objects.create(
            name="Guest Standard",
            price=25000,
            estimated_days=2,
            active=True,
        )
        self.payment_method = PaymentMethod.objects.create(
            name="Guest COD",
            code="GUEST_COD",
            active=True,
        )
        self.category = Category.objects.create(name="Guest Cat", slug="guest-cat")
        self.product = Product.objects.create(
            name="Guest Product A",
            mid="MID-GUEST-001",
            slug="guest-product-a",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Hộp",
            in_stock=50,
            is_published=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=1,
            unit_name="Hộp",
            unit_order=0,
            price_value=80000,
            is_default=True,
            is_published=True,
        )
        MedicineBatch.objects.create(
            batch_number="BATCH-GUEST-001",
            product_variant=self.variant,
            import_date=timezone.now().date() - timedelta(days=3),
            expiry_date=timezone.now().date() + timedelta(days=200),
            quantity=50,
            remaining_quantity=50,
        )

    def _delivery_body(self):
        return {
            "orderer": {"name": "Khách Lẻ", "phone": "0901234567", "email": "guest@example.com"},
            "recipient": {"name": "Khách Lẻ", "phone": "0901234567"},
            "address": {"province": "HN", "district": "Cầu Giấy", "ward": "Dịch Vọng", "detail": "1 Guest St"},
        }

    def test_guest_cart_current_without_header_is_forbidden(self):
        anon = self.client_class()()
        response = anon.get("/api/store/carts/current/")
        self.assertIn(response.status_code, (401, 403))

    def test_guest_cart_add_and_checkout_creates_order_without_user(self):
        current = self.client.get("/api/store/carts/current/")
        self.assertEqual(current.status_code, 200)
        self.assertIsNone(current.data.get("user_id"))
        self.assertEqual(str(current.data.get("guest_session_id")), self.guest_session_id)
        v0 = current.data["version"]

        add = self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        v1 = add.data["version"]

        ship = self.client.post(
            "/api/store/carts/select-shipping/",
            {
                "expected_version": v1,
                "shipping_method_id": self.shipping_method.id,
            },
            format="json",
        )
        self.assertEqual(ship.status_code, 200)
        v2 = ship.data["version"]

        checkout = self.client.post(
            "/api/store/carts/checkout/",
            {
                "expected_version": v2,
                "payment_method_id": self.payment_method.id,
                "delivery": self._delivery_body(),
            },
            format="json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        order = Order.objects.get(order_number=checkout.data["order_number"])
        self.assertIsNone(order.user_id)
        self.assertIn("Người nhận:", order.shipping_address)

    def test_merge_guest_cart_into_user_on_login(self):
        current = self.client.get("/api/store/carts/current/").data
        v0 = current["version"]
        self.client.post(
            "/api/store/carts/items/",
            {
                "expected_version": v0,
                "product_variant_id": self.variant.id,
                "product_variant_unit_id": self.unit.id,
                "quantity": 2,
            },
            format="json",
        )

        user_model = get_user_model()
        user = user_model.objects.create_user(
            email="guest-merge-user@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=user)
        merge = self.client.post("/api/store/carts/merge-guest/", {}, format="json")
        self.assertEqual(merge.status_code, 200)
        self.assertEqual(merge.data["items"][0]["quantity"], 2)
        guest_cart = Cart.objects.filter(guest_session_id=self.guest_session_id, status=Cart.ABANDONED).first()
        self.assertIsNotNone(guest_cart)


class StoreImportCsvHelperTests(SimpleTestCase):
    def test_parse_sale_units_from_csv_json_string(self):
        from storeApp.management.commands.catalog_import.store_import_csv import (
            _build_variant_payloads_from_sale_units,
            _parse_json_field,
        )

        raw = (
            '[{"unitName":"Hộp","quantityInBase":120,"unitOrder":0,'
            '"isDefault":true,"priceValue":330000,"priceDisplay":"330.000đ / Hộp"}]'
        )
        sale_units = _parse_json_field(raw, default=[])
        self.assertEqual(len(sale_units), 1)
        payloads = _build_variant_payloads_from_sale_units(sale_units, "Hộp x 120")
        self.assertEqual(payloads[0]["units"][0]["quantity_in_base"], 120)
        self.assertEqual(payloads[0]["units"][0]["price_value"], 330000.0)

    def test_ensure_unit_pricing_uses_row_fallback_before_random(self):
        from storeApp.management.commands.catalog_import.store_import_pricing import ensure_unit_pricing

        units = [
            {
                "unit_name": "Hộp",
                "quantity_in_base": 40,
                "price_value": 0,
                "price_display": None,
                "is_default": True,
            }
        ]
        ensure_unit_pricing(units, fallback_price=400000, fallback_display="400.000đ / Hộp")
        self.assertEqual(units[0]["price_value"], 400000.0)

    def test_smart_random_scales_with_quantity_in_base(self):
        from storeApp.management.commands.catalog_import.store_import_pricing import smart_random_unit_price

        random.seed(42)
        hop = smart_random_unit_price("Hộp", 40)
        vien = smart_random_unit_price("Viên", 1)
        self.assertGreaterEqual(hop, 40_000)
        self.assertLessEqual(vien, 15_000)
        self.assertGreater(hop, vien)

    def test_infer_sibling_price_for_zero_unit(self):
        from storeApp.management.commands.catalog_import.store_import_pricing import ensure_unit_pricing

        units = [
            {"unit_name": "Viên", "quantity_in_base": 1, "price_value": 5000, "is_default": False},
            {"unit_name": "Hộp", "quantity_in_base": 40, "price_value": 0, "is_default": True},
        ]
        ensure_unit_pricing(units, fallback_price=0, use_smart_random=False)
        self.assertEqual(units[1]["price_value"], 200000.0)

    def test_batch_quantity_scales_with_quantity_in_base(self):
        from storeApp.management.commands.catalog_import.store_import_csv import _compute_synthetic_batch_quantity

        qty = _compute_synthetic_batch_quantity(40, 10, 10)
        self.assertEqual(qty, 400)

    def test_import_price_per_base_unit_from_sale_unit(self):
        from storeApp.management.commands.catalog_import.store_import_csv import _compute_import_price_per_base_unit

        price = _compute_import_price_per_base_unit(425000, 40)
        self.assertEqual(price, Decimal("10625.00"))
