from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

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

    def test_search_returns_items_facets_and_meta(self):
        response = self.client.get("/api/store/search/?q=cảm cúm&page=1&page_size=2")
        self.assertEqual(response.status_code, 200)

        self.assertIn("items", response.data)
        self.assertIn("facets", response.data)
        self.assertIn("meta", response.data)
        self.assertEqual(response.data["meta"]["page"], 1)
        self.assertEqual(response.data["meta"]["page_size"], 2)
        self.assertEqual(response.data["meta"]["total"], 2)
        self.assertEqual(len(response.data["items"]), 2)

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
        self.assertEqual(price_counts["100k_300k"], 1)
        self.assertEqual(price_counts["300k_500k"], 0)
        self.assertEqual(price_counts["over_500k"], 1)
        self.assertEqual(stock_counts[True], 2)
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
